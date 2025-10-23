from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping, Sequence, Set as AbstractSet
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs, utils
from ..services.rules import collect_roster_warnings, unit_is_hero

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rosters", tags=["rosters"])
templates = Jinja2Templates(directory="app/templates")

ABILITY_NAME_MAX_LENGTH = 60


def _unit_eager_options() -> tuple:
    return (
        selectinload(models.Unit.weapon_links)
        .selectinload(models.UnitWeapon.weapon)
        .selectinload(models.Weapon.parent)
        .selectinload(models.Weapon.parent),
        selectinload(models.Unit.default_weapon)
        .selectinload(models.Weapon.parent)
        .selectinload(models.Weapon.parent),
        selectinload(models.Unit.abilities).selectinload(models.UnitAbility.ability),
    )


def _normalized_trait_identifier(slug: str | None) -> str | None:
    if slug is None:
        return None
    identifier = costs.ability_identifier(slug)
    if identifier:
        return identifier
    text = str(slug).strip()
    if not text:
        return None
    return text.casefold()


def _is_hidden_trait(slug: str | None) -> bool:
    normalized = _normalized_trait_identifier(slug)
    return bool(normalized and normalized in utils.HIDDEN_TRAIT_SLUGS)


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, bool)) or value is None:
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return 0.0
        return value
    if isinstance(value, Decimal):
        numeric = float(value)
        if not math.isfinite(numeric):
            return 0.0
        return numeric
    if isinstance(value, Mapping):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, AbstractSet):
        return [_json_safe(item) for item in value]
    return None


def _ensure_roster_view_access(roster: models.Roster, user: models.User) -> None:
    if user.is_admin:
        return
    if roster.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do rozpiski")


def _ensure_roster_edit_access(roster: models.Roster, user: models.User) -> None:
    if user.is_admin:
        return
    if roster.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Brak dostępu do rozpiski")


def _ordered_roster_units(db: Session, roster: models.Roster) -> list[models.RosterUnit]:
    return (
        db.execute(
            select(models.RosterUnit)
            .where(models.RosterUnit.roster_id == roster.id)
            .order_by(models.RosterUnit.position, models.RosterUnit.id)
        )
        .scalars()
        .all()
    )
@router.get("", response_class=HTMLResponse)
def list_rosters(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = (
        select(models.Roster)
        .options(
            selectinload(models.Roster.army),
            selectinload(models.Roster.owner),
        )
        .order_by(models.Roster.created_at.desc())
    )
    if not current_user.is_admin:
        query = query.where(
            or_(
                models.Roster.owner_id == current_user.id,
                models.Roster.owner_id.is_(None),
            )
        )
    rosters = db.execute(query).scalars().all()
    mine, global_items, others = utils.split_owned(rosters, current_user)
    return templates.TemplateResponse(
        "rosters_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
            "others": others,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_roster_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    query = select(models.Army).order_by(models.Army.name)
    if not current_user.is_admin:
        query = query.where(
            or_(
                models.Army.owner_id == current_user.id,
                models.Army.owner_id.is_(None),
            )
        )
    armies = db.execute(query).scalars().all()
    return templates.TemplateResponse(
        "roster_form.html",
        {
            "request": request,
            "user": current_user,
            "armies": armies,
            "error": None,
        },
    )


@router.post("/new")
def create_roster(
    request: Request,
    name: str = Form(...),
    army_id: int = Form(...),
    points_limit: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    if not current_user.is_admin and army.owner_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do armii")
    if points_limit is None:
        limit_value = 1000
    else:
        stripped_limit = points_limit.strip()
        limit_value = int(stripped_limit) if stripped_limit else 1000
    roster = models.Roster(
        name=name,
        army=army,
        points_limit=limit_value,
        owner_id=current_user.id,
    )
    db.add(roster)
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.get("/{roster_id}", response_class=HTMLResponse)
def edit_roster(
    roster_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster_stmt = (
        select(models.Roster)
        .options(
            selectinload(models.Roster.army),
            selectinload(models.Roster.roster_units).options(
                selectinload(models.RosterUnit.unit).options(*_unit_eager_options())
            )
        )
        .where(models.Roster.id == roster_id)
    )
    roster = (
        db.execute(roster_stmt)
        .scalars()
        .unique()
        .one_or_none()
    )
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    selected_id = request.query_params.get("selected")

    uncached_units = [
        roster_unit
        for roster_unit in roster.roster_units
        if getattr(roster_unit, "cached_cost", None) is None
    ]
    if uncached_units:
        costs.update_cached_costs(uncached_units)
    available_units_stmt = (
        select(models.Unit)
        .where(models.Unit.army_id == roster.army_id)
        .options(*_unit_eager_options())
        .order_by(models.Unit.name)
    )
    available_units = (
        db.execute(available_units_stmt)
        .scalars()
        .unique()
        .all()
    )
    unit_data_cache: dict[int, dict[str, Any]] = {}
    unit_payloads: dict[int, dict[str, Any]] = {}

    def _unit_cache_value(unit: models.Unit, key: str, factory: Callable[[], Any]) -> Any:
        store = unit_data_cache.setdefault(unit.id, {})
        if key in store:
            logger.debug(
                "Reusing cached value for unit_id=%s key=%s", unit.id, key
            )
            return store[key]
        value = factory()
        store[key] = value
        logger.debug("Caching value for unit_id=%s key=%s", unit.id, key)
        return value

    def _unit_payload(unit: models.Unit) -> dict[str, Any]:
        if unit.id in unit_payloads:
            return unit_payloads[unit.id]
        weapon_options = _unit_cache_value(
            unit, "weapon_options", lambda: _unit_weapon_options(unit)
        )
        passive_items = _unit_cache_value(
            unit, "passive_entries", lambda: _passive_entries(unit)
        )
        active_items = _unit_cache_value(
            unit, "ability_active", lambda: _ability_entries(unit, "active")
        )
        aura_items = _unit_cache_value(
            unit, "ability_aura", lambda: _ability_entries(unit, "aura")
        )
        default_summary = _unit_cache_value(
            unit,
            "default_summary",
            lambda: _default_loadout_summary(unit),
        )
        payload = {
            "weapon_options": weapon_options,
            "passive_items": passive_items,
            "active_items": active_items,
            "aura_items": aura_items,
            "default_summary": default_summary,
        }
        unit_payloads[unit.id] = payload
        return payload

    available_unit_options = []
    for unit in available_units:
        payload = _unit_payload(unit)
        weapon_options = payload["weapon_options"]
        passive_items = payload["passive_items"]
        active_items = payload["active_items"]
        aura_items = payload["aura_items"]
        default_summary = payload["default_summary"]
        typical_models = unit.typical_model_count
        cost_per_model = costs.unit_total_cost(unit)
        available_unit_options.append(
            {
                "unit": unit,
                "weapon_options": weapon_options,
                "default_summary": default_summary,
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "unit_cost_per_model": cost_per_model,
                "unit_cost_total": costs.unit_typical_total_cost(
                    unit,
                    typical_models,
                    per_model=cost_per_model,
                ),
                "typical_models": typical_models,
            }
        )

    roster_items = []
    sanitized_loadouts: dict[int, dict[str, Any]] = {}
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        payload = _unit_payload(unit)
        weapon_options = payload["weapon_options"]
        passive_items = payload["passive_items"]
        active_items = payload["active_items"]
        aura_items = payload["aura_items"]
        default_summary = payload["default_summary"]
        loadout = _roster_unit_loadout(
            roster_unit,
            weapon_options=weapon_options,
            active_items=active_items,
            aura_items=aura_items,
            passive_items=passive_items,
        )
        if roster_unit.id is not None:
            sanitized_loadouts[roster_unit.id] = loadout
        classification = _roster_unit_classification(roster_unit, loadout)
        class_slug = (
            str(classification.get("slug") or "").strip().casefold()
            if classification
            else "none"
        )
        is_hero = unit_is_hero(unit, roster_unit, loadout)
        selected_passives = _selected_passive_entries(
            roster_unit, loadout, passive_items, classification
        )
        selected_actives = _selected_ability_entries(loadout, active_items, "active")
        selected_auras = _selected_ability_entries(loadout, aura_items, "aura")
        roster_items.append(
            {
                "instance": roster_unit,
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "selected_passive_items": selected_passives,
                "selected_active_items": selected_actives,
                "selected_aura_items": selected_auras,
                "default_summary": default_summary,
                "weapon_options": weapon_options,
                "loadout": loadout,
                "loadout_summary": _loadout_display_summary(roster_unit, loadout, weapon_options),
                "base_cost_per_model": _unit_cache_value(
                    unit,
                    f"base_cost::{class_slug}",
                    lambda: _base_cost_per_model(unit, classification),
                ),
                "classification": classification,
                "is_hero": is_hero,
            }
        )
    non_hero_unit_count = sum(
        1
        for item in roster_items
        if getattr(item.get("instance"), "unit", None) is not None
        and not item.get("is_hero", False)
    )
    total_cost = costs.roster_total(roster)
    warnings = collect_roster_warnings(
        roster, total_cost=total_cost, loadouts=sanitized_loadouts
    )
    can_edit = current_user.is_admin or roster.owner_id == current_user.id
    can_delete = can_edit

    return templates.TemplateResponse(
        "roster_edit.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "available_units": available_unit_options,
            "roster_items": roster_items,
            "non_hero_unit_count": non_hero_unit_count,
            "total_cost": total_cost,
            "error": None,
            "can_edit": can_edit,
            "can_delete": can_delete,
            "warnings": warnings,
            "selected_id": selected_id,
            "unit_payloads": unit_payloads,
        },
    )


@router.post("/{roster_id}/update")
def update_roster(
    roster_id: int,
    name: str = Form(...),
    points_limit: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)
    roster.name = name
    roster.points_limit = int(points_limit) if points_limit else None
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/delete")
def delete_roster(
    roster_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    db.delete(roster)
    db.commit()
    return RedirectResponse(url="/rosters", status_code=303)


@router.post("/{roster_id}/units/add")
def add_roster_unit(
    roster_id: int,
    request: Request,
    unit_id: int = Form(...),
    count: int = Form(1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    unit = (
        db.execute(
            select(models.Unit)
            .options(*_unit_eager_options())
            .where(models.Unit.id == unit_id)
        )
        .scalars()
        .first()
    )
    if not roster or unit is None or unit.army_id != roster.army_id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    count = max(int(count), 1)
    weapon_options = _unit_weapon_options(unit)
    active_items = _ability_entries(unit, "active")
    aura_items = _ability_entries(unit, "aura")
    passive_items = _passive_entries(unit)
    role_slug_map = _role_slug_map(unit)
    loadout = _default_loadout_payload(
        unit,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )
    roster_unit = models.RosterUnit(
        roster=roster,
        unit=unit,
        count=count,
    )

    max_position = (
        db.execute(
            select(func.max(models.RosterUnit.position)).where(
                models.RosterUnit.roster_id == roster.id
            )
        ).scalar_one_or_none()
        or -1
    )
    roster_unit.position = max_position + 1

    totals = costs.roster_unit_role_totals(roster_unit, loadout)
    warrior_total = float(totals.get("wojownik") or 0.0)
    shooter_total = float(totals.get("strzelec") or 0.0)
    classification = _roster_unit_classification(
        roster_unit, loadout, totals=totals
    )
    loadout = (
        _apply_classification_to_loadout(
            loadout, classification, role_slug_map=role_slug_map
        )
        or loadout
    )

    roster_unit.extra_weapons_json = json.dumps(loadout, ensure_ascii=False)
    roster_unit.cached_cost = max(warrior_total, shooter_total)
    db.add(roster_unit)
    db.flush()
    db.commit()

    accept_header = (request.headers.get("accept") or "").lower()
    if "application/json" in accept_header:
        loadout_payload = _roster_unit_loadout(
            roster_unit,
            weapon_options=weapon_options,
            active_items=active_items,
            aura_items=aura_items,
            passive_items=passive_items,
        )
        selected_passives = _selected_passive_entries(
            roster_unit, loadout_payload, passive_items, classification
        )
        selected_actives = _selected_ability_entries(
            loadout_payload, active_items, "active"
        )
        selected_auras = _selected_ability_entries(loadout_payload, aura_items, "aura")
        total_cost = costs.roster_total(roster)
        loadout_mapping = (
            {roster_unit.id: loadout_payload} if roster_unit.id is not None else None
        )
        warnings = collect_roster_warnings(
            roster, total_cost=total_cost, loadouts=loadout_mapping
        )
        loadout_json = json.dumps(loadout_payload, ensure_ascii=False)
        default_summary = _default_loadout_summary(unit)
        loadout_summary = _loadout_display_summary(
            roster_unit,
            loadout_payload,
            weapon_options,
        )
        base_cost_per_model = _base_cost_per_model(unit, classification)
        roster_item = {
            "id": roster_unit.id,
            "count": roster_unit.count,
            "cached_cost": roster_unit.cached_cost,
            "custom_name": roster_unit.custom_name or "",
            "unit_id": unit.id,
            "unit_name": unit.name,
            "unit_quality": unit.quality,
            "unit_defense": unit.defense,
            "unit_toughness": unit.toughness,
            "unit_flags": unit.flags or "",
            "default_summary": default_summary,
            "loadout_summary": loadout_summary,
            "weapon_options": weapon_options,
            "passive_items": passive_items,
            "active_items": active_items,
            "aura_items": aura_items,
            "selected_passive_items": selected_passives,
            "selected_active_items": selected_actives,
            "selected_aura_items": selected_auras,
            "loadout": loadout_payload,
            "classification": classification,
            "base_cost_per_model": base_cost_per_model,
        }
        payload = {
            "unit": {
                "id": roster_unit.id,
                "count": roster_unit.count,
                "custom_name": roster_unit.custom_name or "",
                "cached_cost": roster_unit.cached_cost,
                "loadout_json": loadout_json,
                "loadout_summary": loadout_summary,
                "default_summary": default_summary,
                "base_cost_per_model": base_cost_per_model,
                "classification": classification,
                "selected_passive_items": selected_passives,
                "selected_active_items": selected_actives,
                "selected_aura_items": selected_auras,
                "unit_cache_id": unit.id,
            },
            "roster_item": roster_item,
            "warnings": warnings,
            "total_cost": total_cost,
        }
        return JSONResponse(_json_safe(payload))
    return RedirectResponse(
        url=f"/rosters/{roster.id}?selected={roster_unit.id}",
        status_code=303,
    )


@router.post("/{roster_id}/units/{roster_unit_id}/move")
def move_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    direction: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    normalized_direction = (direction or "").strip().lower()
    if normalized_direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Nieprawidłowy kierunek")

    current_position = roster_unit.position or 0
    base_neighbor_query = select(models.RosterUnit.position).where(
        models.RosterUnit.roster_id == roster.id,
        models.RosterUnit.id != roster_unit.id,
    )
    if normalized_direction == "up":
        neighbor_position = (
            db.execute(
                base_neighbor_query.where(
                    models.RosterUnit.position < current_position,
                )
                .order_by(models.RosterUnit.position.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
    else:
        neighbor_position = (
            db.execute(
                base_neighbor_query.where(
                    models.RosterUnit.position > current_position,
                )
                .order_by(models.RosterUnit.position)
                .limit(1)
            )
            .scalars()
            .first()
        )

    if neighbor_position is None:
        return RedirectResponse(
            url=f"/rosters/{roster.id}?selected={roster_unit.id}",
            status_code=303,
        )

    target_position = neighbor_position
    if target_position < current_position:
        db.execute(
            update(models.RosterUnit)
            .where(
                models.RosterUnit.roster_id == roster.id,
                models.RosterUnit.position >= target_position,
                models.RosterUnit.position < current_position,
            )
            .values(position=models.RosterUnit.position + 1)
            .execution_options(synchronize_session=False)
        )
    elif target_position > current_position:
        db.execute(
            update(models.RosterUnit)
            .where(
                models.RosterUnit.roster_id == roster.id,
                models.RosterUnit.position <= target_position,
                models.RosterUnit.position > current_position,
            )
            .values(position=models.RosterUnit.position - 1)
            .execution_options(synchronize_session=False)
        )
    else:
        return RedirectResponse(
            url=f"/rosters/{roster.id}?selected={roster_unit.id}",
            status_code=303,
        )

    roster_unit.position = target_position
    db.commit()
    return RedirectResponse(
        url=f"/rosters/{roster.id}?selected={roster_unit.id}",
        status_code=303,
    )


@router.post("/{roster_id}/units/{roster_unit_id}/update")
def update_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    request: Request,
    count: int = Form(...),
    loadout_json: str | None = Form(None),
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = (
        db.execute(
            select(models.RosterUnit)
            .options(
                selectinload(models.RosterUnit.unit).options(*_unit_eager_options())
            )
            .where(models.RosterUnit.id == roster_unit_id)
        )
        .scalars()
        .first()
    )
    if not roster or roster_unit is None or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    roster_unit.count = max(int(count), 1)
    weapon_options = _unit_weapon_options(roster_unit.unit)
    active_items = _ability_entries(roster_unit.unit, "active")
    aura_items = _ability_entries(roster_unit.unit, "aura")
    passive_items = _passive_entries(roster_unit.unit)
    role_slug_map = _role_slug_map(roster_unit.unit)

    parsed_loadout = _parse_loadout_json(loadout_json)
    loadout = _sanitize_loadout(
        roster_unit.unit,
        roster_unit.count,
        parsed_loadout,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )

    totals = costs.roster_unit_role_totals(roster_unit, loadout)
    warrior_total = float(totals.get("wojownik") or 0.0)
    shooter_total = float(totals.get("strzelec") or 0.0)
    classification = _roster_unit_classification(
        roster_unit, loadout, totals=totals
    )
    loadout = (
        _apply_classification_to_loadout(
            loadout, classification, role_slug_map=role_slug_map
        )
        or loadout
    )
    roster_unit.custom_name = custom_name.strip() if custom_name else None
    roster_unit.extra_weapons_json = json.dumps(loadout, ensure_ascii=False)
    roster_unit.cached_cost = max(warrior_total, shooter_total)
    db.commit()
    accept_header = (request.headers.get("accept") or "").lower()
    if "application/json" in accept_header:
        total_cost = costs.roster_total(roster)
        selected_passives = _selected_passive_entries(
            roster_unit, loadout, passive_items, classification
        )
        selected_actives = _selected_ability_entries(loadout, active_items, "active")
        selected_auras = _selected_ability_entries(loadout, aura_items, "aura")
        loadout_mapping = (
            {roster_unit.id: loadout} if roster_unit.id is not None else None
        )
        warnings = collect_roster_warnings(
            roster, total_cost=total_cost, loadouts=loadout_mapping
        )
        payload = {
            "unit": {
                "id": roster_unit.id,
                "count": roster_unit.count,
                "custom_name": roster_unit.custom_name or "",
                "cached_cost": roster_unit.cached_cost,
                "loadout_json": json.dumps(loadout, ensure_ascii=False),
                "loadout_summary": _loadout_display_summary(
                    roster_unit,
                    loadout,
                    weapon_options,
                ),
                "default_summary": _default_loadout_summary(roster_unit.unit),
                "base_cost_per_model": _base_cost_per_model(
                    roster_unit.unit, classification
                ),
                "classification": classification,
                "selected_passive_items": selected_passives,
                "selected_active_items": selected_actives,
                "selected_aura_items": selected_auras,
            },
            "roster": {"total_cost": total_cost},
            "warnings": warnings,
        }
        return JSONResponse(_json_safe(payload))
    return RedirectResponse(
        url=f"/rosters/{roster.id}?selected={roster_unit.id}",
        status_code=303,
    )


@router.post("/{roster_id}/units/{roster_unit_id}/duplicate")
def duplicate_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    clone = models.RosterUnit(
        roster=roster,
        unit=roster_unit.unit,
        count=roster_unit.count,
        extra_weapons_json=roster_unit.extra_weapons_json,
        custom_name=roster_unit.custom_name,
    )
    clone.cached_cost = roster_unit.cached_cost
    if clone.cached_cost is None:
        clone.cached_cost = costs.roster_unit_cost(clone)
    insert_position = (roster_unit.position or 0) + 1
    db.execute(
        update(models.RosterUnit)
        .where(
            models.RosterUnit.roster_id == roster.id,
            models.RosterUnit.position >= insert_position,
        )
        .values(position=models.RosterUnit.position + 1)
        .execution_options(synchronize_session=False)
    )
    clone.position = insert_position
    db.add(clone)
    db.commit()
    return RedirectResponse(
        url=f"/rosters/{roster.id}?selected={clone.id}",
        status_code=303,
    )


@router.post("/{roster_id}/units/{roster_unit_id}/delete")
def delete_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    removed_position = roster_unit.position or 0
    db.delete(roster_unit)
    db.flush()
    db.execute(
        update(models.RosterUnit)
        .where(
            models.RosterUnit.roster_id == roster.id,
            models.RosterUnit.position > removed_position,
        )
        .values(position=models.RosterUnit.position - 1)
    )
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)
def _default_loadout_summary(unit: models.Unit) -> str:
    parts: list[str] = []
    for weapon, count in unit.default_weapon_loadout:
        label = f"{weapon.effective_name} x{count}" if count > 1 else weapon.effective_name
        parts.append(label)
    return ", ".join(parts) if parts else "-"


def _unit_weapon_options(unit: models.Unit) -> list[dict]:
    options: list[dict] = []
    seen: set[int] = set()
    flags = utils.parse_flags(unit.flags)
    primary_id: int | None = None
    if getattr(unit, "default_weapon_id", None):
        primary_id = unit.default_weapon_id
    elif getattr(unit, "default_weapon", None) and getattr(unit.default_weapon, "id", None):
        primary_id = unit.default_weapon.id
    for link in getattr(unit, "weapon_links", []):
        if link.weapon_id is None or link.weapon is None:
            continue
        if link.weapon_id in seen:
            continue
        cost_value = costs.weapon_cost(link.weapon, unit.quality, flags)
        default_count = getattr(link, "default_count", None)
        try:
            default_count = int(default_count) if default_count is not None else None
        except (TypeError, ValueError):
            default_count = None
        is_primary = bool(getattr(link, "is_primary", False))
        if (
            not is_primary
            and primary_id is not None
            and link.weapon_id == primary_id
            and (default_count or 0) > 0
        ):
            is_primary = True
        options.append(
            {
                "id": link.weapon_id,
                "name": link.weapon.effective_name,
                "is_default": bool(getattr(link, "is_default", False)),
                "is_primary": is_primary,
                "cost": cost_value,
                "default_count": default_count,
                "range": link.weapon.effective_range or link.weapon.range or "-",
                "attacks": getattr(link.weapon, "display_attacks", None)
                or link.weapon.effective_attacks,
                "ap": link.weapon.effective_ap,
                "traits": link.weapon.effective_tags or link.weapon.tags or "",
            }
        )
        seen.add(link.weapon_id)
    if unit.default_weapon_id and unit.default_weapon_id not in seen and unit.default_weapon:
        cost_value = costs.weapon_cost(unit.default_weapon, unit.quality, flags)
        options.append(
            {
                "id": unit.default_weapon_id,
                "name": unit.default_weapon.effective_name,
                "is_default": True,
                "is_primary": bool(primary_id == unit.default_weapon_id),
                "cost": cost_value,
                "default_count": 1,
                "range": unit.default_weapon.effective_range
                or unit.default_weapon.range
                or "-",
                "attacks": getattr(unit.default_weapon, "display_attacks", None)
                or unit.default_weapon.effective_attacks,
                "ap": unit.default_weapon.effective_ap,
                "traits": unit.default_weapon.effective_tags
                or unit.default_weapon.tags
                or "",
            }
        )
    options.sort(key=lambda item: (not item["is_default"], item["name"].casefold()))
    return options
def _passive_entries(unit: models.Unit) -> list[dict]:
    payload = utils.passive_flags_to_payload(unit.flags)
    entries: list[dict] = []
    flags = utils.parse_flags(unit.flags)
    unit_traits = costs.flags_to_ability_list(flags)
    default_weapons = costs.unit_default_weapons(unit)
    for item in payload:
        if not item:
            continue
        slug = str(item.get("slug") or "").strip()
        if _is_hidden_trait(slug):
            continue
        label = item.get("label") or slug
        value = item.get("value")
        description = item.get("description") or ""
        is_mandatory = bool(item.get("is_mandatory", False))
        is_default = bool(item.get("is_default", False)) or is_mandatory
        try:
            cost_value = float(
                costs.ability_cost_from_name(
                    label or slug,
                    value,
                    unit_traits,
                    toughness=unit.toughness,
                    quality=unit.quality,
                    defense=unit.defense,
                    weapons=default_weapons,
                )
            )
        except Exception:  # pragma: no cover - fallback for unexpected input
            cost_value = float(
                costs.ability_cost_from_name(
                    slug,
                    value,
                    unit_traits,
                    toughness=unit.toughness,
                    quality=unit.quality,
                    defense=unit.defense,
                    weapons=default_weapons,
                )
            )
        entries.append(
            {
                "slug": slug,
                "value": "" if value is None else str(value),
                "label": label,
                "description": description,
                "cost": cost_value,
                "is_default": is_default,
                "default_count": 1 if is_default else 0,
                "is_mandatory": is_mandatory,
            }
        )
    return entries


def _passive_labels(unit: models.Unit) -> list[str]:
    return [
        entry["label"]
        for entry in _passive_entries(unit)
        if entry.get("label")
    ]


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return default
    return number


def _ability_loadout_key(ability_id: Any, value: Any | None) -> str:
    if ability_id is None:
        return ""
    base = str(ability_id)
    if value is None:
        return base
    if isinstance(value, bool):
        variant = "1" if value else "0"
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            variant = str(int(value))
        else:
            variant = str(value)
    else:
        variant = str(value).strip()
    if not variant:
        return base
    return f"{base}:{variant}"


def _split_ability_loadout_key(key: Any) -> tuple[str, str | None]:
    text = str(key).strip()
    if not text:
        return "", None
    if ":" in text:
        ability_id, variant = text.split(":", 1)
        return ability_id, variant
    return text, None


def _loadout_counts(
    loadout: dict[str, Any] | None, section: str
) -> dict[str, int]:
    result: dict[str, int] = {}
    if not isinstance(loadout, dict):
        return result
    raw_section = loadout.get(section)
    if isinstance(raw_section, dict):
        items = raw_section.items()
    elif isinstance(raw_section, list):
        items = []
        for entry in raw_section:
            if not isinstance(entry, dict):
                continue
            if section == "passive":
                key = entry.get("slug") or entry.get("id")
            else:
                key = (
                    entry.get("loadout_key")
                    or entry.get("key")
                    or entry.get("id")
                    or entry.get("ability_id")
                )
                if key is None:
                    ability_id = entry.get("ability_id")
                    value = entry.get("value")
                    if ability_id is not None:
                        key = _ability_loadout_key(ability_id, value)
            if key is None:
                continue
            items.append((key, entry.get("count")))
    else:
        return result
    for key, raw_value in items:
        if key is None:
            continue
        key_str = str(key)
        count = _coerce_int(raw_value, 0)
        if count < 0:
            count = 0
        result[key_str] = count
    return result


def _loadout_passive_flags(loadout: dict[str, Any] | None) -> dict[str, int]:
    counts = _loadout_counts(loadout, "passive")
    return {key: 1 if value > 0 else 0 for key, value in counts.items()}


def _selected_passive_entries(
    roster_unit: models.RosterUnit,
    loadout: dict[str, Any] | None,
    passive_items: list[dict] | None,
    classification: dict[str, Any] | None = None,
) -> list[dict]:
    entries = passive_items if passive_items is not None else _passive_entries(roster_unit.unit)
    flags = _loadout_passive_flags(loadout)
    selected: list[dict] = []
    seen_slugs: set[str] = set()
    seen_identifiers: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        identifier = costs.ability_identifier(slug)
        if _is_hidden_trait(slug):
            seen_slugs.add(slug)
            if identifier:
                seen_identifiers.add(identifier)
            continue
        default_flag = 1 if entry.get("is_default") or entry.get("default_count") else 0
        is_mandatory = bool(entry.get("is_mandatory", False))
        selected_flag = flags.get(slug, default_flag)
        if is_mandatory:
            selected_flag = 1
        if selected_flag <= 0:
            seen_slugs.add(slug)
            if identifier:
                seen_identifiers.add(identifier)
            continue
        item = dict(entry)
        item["selected"] = True
        item["count"] = 1
        if is_mandatory:
            item["is_mandatory"] = True
        selected.append(item)
        seen_slugs.add(slug)
        if identifier:
            seen_identifiers.add(identifier)
    for slug, flag in flags.items():
        slug_value = str(slug).strip()
        if not slug_value or flag <= 0:
            if slug_value:
                seen_slugs.add(slug_value)
                identifier = costs.ability_identifier(slug_value)
                if identifier:
                    seen_identifiers.add(identifier)
            continue
        identifier = costs.ability_identifier(slug_value)
        if _is_hidden_trait(slug_value):
            seen_slugs.add(slug_value)
            if identifier:
                seen_identifiers.add(identifier)
            continue
        if slug_value in seen_slugs or (identifier and identifier in seen_identifiers):
            continue
        selected.append(
            {
                "slug": slug_value,
                "label": slug_value,
                "description": "",
                "selected": True,
                "count": 1,
            }
        )
        seen_slugs.add(slug_value)
        if identifier:
            seen_identifiers.add(identifier)
    if isinstance(classification, dict):
        class_slug = str(classification.get("slug") or "").strip()
        if class_slug:
            identifier = costs.ability_identifier(class_slug)
            if _is_hidden_trait(class_slug):
                seen_slugs.add(class_slug)
                if identifier:
                    seen_identifiers.add(identifier)
                return selected
            if class_slug not in seen_slugs and (
                not identifier or identifier not in seen_identifiers
            ):
                label = classification.get("label") or class_slug
                entry = {
                    "slug": class_slug,
                    "label": label,
                    "description": "",
                    "selected": True,
                    "count": 1,
                }
                selected.append(entry)
                seen_slugs.add(class_slug)
                if identifier:
                    seen_identifiers.add(identifier)
    return selected


def _role_slug_map(unit: models.Unit | None) -> dict[str, str]:
    if unit is None:
        return {}
    mapping: dict[str, str] = {}
    flags = utils.parse_flags(getattr(unit, "flags", None))
    for raw_key in flags.keys():
        if raw_key is None:
            continue
        value = str(raw_key).strip()
        if not value:
            continue
        while value.endswith(("?", "!")):
            value = value[:-1].strip()
        identifier = costs.ability_identifier(value)
        if identifier in costs.ROLE_SLUGS and identifier not in mapping:
            mapping[identifier] = value
    return mapping


def _apply_classification_to_loadout(
    loadout: dict[str, Any] | None,
    classification: dict[str, Any] | None,
    *,
    role_slug_map: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(loadout, dict):
        return loadout

    passive_section = loadout.get("passive")
    if not isinstance(passive_section, dict):
        passive_section = {}
        loadout["passive"] = passive_section

    target_identifier: str | None = None
    target_key: str | None = None
    if isinstance(classification, dict):
        raw_slug = classification.get("slug")
        if isinstance(raw_slug, str):
            normalized = costs.ability_identifier(raw_slug)
            if normalized in costs.ROLE_SLUGS:
                target_identifier = normalized
                stripped = raw_slug.strip()
                target_key = stripped or normalized

    existing_map: dict[str, str] = {}
    for key in list(passive_section.keys()):
        identifier = costs.ability_identifier(key)
        if identifier not in costs.ROLE_SLUGS:
            continue
        if identifier not in existing_map:
            existing_map[identifier] = str(key)
        if not target_identifier or identifier != target_identifier:
            passive_section.pop(key, None)

    if target_identifier:
        preferred_map = dict(existing_map)
        if role_slug_map:
            for ident, slug in role_slug_map.items():
                if ident in costs.ROLE_SLUGS and ident not in preferred_map:
                    preferred_map[ident] = slug
        candidate = preferred_map.get(target_identifier)
        if candidate:
            target_key = candidate
        if target_key is None:
            target_key = target_identifier
        cleaned_key = str(target_key).strip()
        while cleaned_key.endswith(("?", "!")):
            cleaned_key = cleaned_key[:-1].strip()
        passive_section[cleaned_key or target_identifier] = 1

    return loadout


def _selected_ability_entries(
    loadout: dict[str, Any] | None,
    ability_items: list[dict] | None,
    section: str,
) -> list[dict]:
    entries = ability_items if ability_items is not None else []
    counts = _loadout_counts(loadout, section)
    name_map: dict[str, str] = {}
    if isinstance(loadout, dict):
        name_map = _extract_label_map(loadout.get(f"{section}_labels"))
    selected: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry or entry.get("ability_id") is None:
            continue
        ability_id = entry.get("ability_id")
        loadout_key = entry.get("loadout_key")
        if not loadout_key:
            loadout_key = _ability_loadout_key(ability_id, entry.get("value"))
        if not loadout_key:
            continue
        key = str(loadout_key)
        default_count = _coerce_int(entry.get("default_count") or 0, 0)
        stored = counts.get(key, default_count)
        if stored <= 0:
            seen.add(key)
            continue
        item = dict(entry)
        item["count"] = stored
        item["loadout_key"] = key

        custom_name = item.get("custom_name") or name_map.get(key)
        if isinstance(custom_name, str):
            normalized = custom_name.strip()
            if normalized:
                item["custom_name"] = normalized
            elif "custom_name" in item:
                item.pop("custom_name", None)

        selected.append(item)
        seen.add(key)
    for key, value in counts.items():
        if key in seen or value <= 0:
            continue
        ability_id_str, variant = _split_ability_loadout_key(key)
        ability_id_value: Any = ability_id_str
        try:
            ability_id_value = int(ability_id_str)
        except (TypeError, ValueError):
            try:
                ability_id_value = int(float(ability_id_str))
            except (TypeError, ValueError):
                ability_id_value = ability_id_str
        fallback = {
            "ability_id": ability_id_value,
            "label": str(key),
            "description": "",
            "count": value,
            "value": variant,
            "loadout_key": key,
        }
        custom_name = name_map.get(str(key))
        if isinstance(custom_name, str):
            normalized = custom_name.strip()
            if normalized:
                fallback["custom_name"] = normalized

        selected.append(fallback)

    return selected


def _ability_label_with_count(entry: dict) -> str:
    base_label = entry.get("label") or entry.get("raw") or entry.get("slug") or ""
    custom = str(entry.get("custom_name") or "").strip()
    if custom:
        label = f"{custom} [{base_label}]" if base_label else custom
    else:
        label = base_label
    count = _coerce_int(entry.get("count"), 0)
    if count > 1:
        return f"{label} ×{count}"
    return label


def _ability_entries(unit: models.Unit, ability_type: str) -> list[dict]:
    entries: list[dict] = []
    payload = ability_registry.unit_ability_payload(unit, ability_type)
    payload_by_id: dict[int, list[dict]] = {}
    for item in payload:
        ability_id = item.get("ability_id")
        if ability_id is None:
            continue
        try:
            key = int(ability_id)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
        payload_by_id.setdefault(key, []).append(item)
    flags = utils.parse_flags(unit.flags)
    unit_traits = costs.flags_to_ability_list(flags)
    ability_links = [
        link
        for link in getattr(unit, "abilities", [])
        if link.ability and link.ability.type == ability_type
    ]
    ability_links.sort(
        key=lambda link: (
            getattr(link, "position", 0),
            getattr(link, "id", 0) or 0,
        )
    )
    for link in ability_links:
        ability = link.ability
        params: dict[str, Any] = {}
        if link.params_json:
            try:
                params = json.loads(link.params_json)
            except json.JSONDecodeError:  # pragma: no cover - defensive
                params = {}
        value = params.get("value")
        value_str = str(value) if value is not None else None
        payload_entry: dict[str, Any] | None = None
        payload_candidates = payload_by_id.get(ability.id or -1) or []
        if value_str is not None:
            for candidate in payload_candidates:
                if str(candidate.get("value") or "") == value_str:
                    payload_entry = candidate
                    break
        if payload_entry is None and payload_candidates:
            payload_entry = payload_candidates[0]
        payload_entry = payload_entry or {}
        label = payload_entry.get("label") or ability.name or ""
        custom_name = payload_entry.get("custom_name")
        slug = payload_entry.get("slug") or ability_registry.ability_slug(ability) or ""
        raw_label = payload_entry.get("raw") or payload_entry.get("base_label") or label
        if isinstance(custom_name, str):
            custom_name = custom_name.strip() or None
        base_label = payload_entry.get("base_label") or label
        description = payload_entry.get("description") or ability.description or ""
        is_default = payload_entry.get("is_default")
        if is_default is None:
            is_default = False
            if "default" in params:
                is_default = bool(params.get("default"))
            elif "is_default" in params:
                is_default = bool(params.get("is_default"))
        cost_value = costs.ability_cost(
            link,
            unit_traits,
            toughness=unit.toughness,
        )
        entries.append(
            {
                "ability_id": ability.id,
                "label": base_label,
                "raw": raw_label,
                "slug": slug,
                "description": description,
                "cost": cost_value,
                "is_default": bool(is_default),
                "default_count": 1 if bool(is_default) else 0,
                "custom_name": custom_name,
                "value": value,
                "loadout_key": _ability_loadout_key(ability.id, value),
            }
        )
    entries.sort(key=lambda entry: (not entry.get("is_default", False), entry.get("label", "").casefold()))
    return entries


def _base_cost_per_model(
    unit: models.Unit, classification: dict[str, Any] | None = None
) -> float:
    passive_state = costs.compute_passive_state(unit)
    base_traits = [
        trait
        for trait in passive_state.traits
        if costs.ability_identifier(trait) not in costs.ROLE_SLUGS
    ]
    slug: str | None = None
    if isinstance(classification, dict):
        raw_slug = classification.get("slug")
        if isinstance(raw_slug, str):
            normalized = raw_slug.strip().casefold()
            if normalized in costs.ROLE_SLUGS:
                slug = normalized
    if slug:
        base_traits.append(slug)
    base_value = costs.base_model_cost(
        unit.quality,
        unit.defense,
        unit.toughness,
        base_traits,
    )
    passive_cost = 0.0
    trait_tokens: set[str] = set()

    def _add_tokens(value: str | None) -> set[str]:
        tokens: set[str] = set()
        if not value:
            return tokens
        raw_text = str(value).strip()
        if not raw_text:
            return tokens
        tokens.add(raw_text.casefold())
        identifier = costs.ability_identifier(raw_text)
        if identifier:
            tokens.add(identifier)
        normalized = costs.normalize_name(raw_text)
        if normalized:
            tokens.add(normalized)
        return tokens

    for trait in base_traits:
        trait_tokens.update(_add_tokens(trait))
    default_weapons = costs.unit_default_weapons(unit)
    for entry in passive_state.payload:
        slug_value = str(entry.get("slug") or "").strip()
        if not slug_value:
            continue
        if costs.ability_identifier(slug_value) in costs.ROLE_SLUGS:
            continue
        try:
            default_count = int(entry.get("default_count") or 0)
        except (TypeError, ValueError):
            default_count = 0
        if default_count <= 0:
            continue
        entry_tokens = _add_tokens(slug_value)
        entry_tokens.update(_add_tokens(entry.get("label")))
        if trait_tokens.intersection(entry_tokens):
            continue
        label = entry.get("label") or slug_value
        value = entry.get("value")
        passive_cost += costs.ability_cost_from_name(
            label or slug_value,
            value,
            base_traits,
            toughness=unit.toughness,
            quality=unit.quality,
            defense=unit.defense,
            weapons=default_weapons,
        )
        trait_tokens.update(entry_tokens)
    return round(base_value + passive_cost, 2)


def _default_loadout_payload(
    unit: models.Unit,
    weapon_options: list[dict] | None = None,
    active_items: list[dict] | None = None,
    aura_items: list[dict] | None = None,
    passive_items: list[dict] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "weapons": {},
        "active": {},
        "aura": {},
        "passive": {},
        "active_labels": {},
        "aura_labels": {},
    }
    options = weapon_options if weapon_options is not None else _unit_weapon_options(unit)
    for option in options:
        weapon_id = option.get("id")
        if weapon_id is None:
            continue
        try:
            default_count = int(option.get("default_count") or 0)
        except (TypeError, ValueError):
            default_count = 0
        payload["weapons"][str(weapon_id)] = max(default_count, 0)

    for ability_entry, key in (
        (active_items if active_items is not None else _ability_entries(unit, "active"), "active"),
        (aura_items if aura_items is not None else _ability_entries(unit, "aura"), "aura"),
    ):
        for item in ability_entry:
            ability_id = item.get("ability_id")
            if ability_id is None:
                continue
            try:
                default_count = int(item.get("default_count") or 0)
            except (TypeError, ValueError):
                default_count = 0
            entry_key = item.get("loadout_key")
            if not entry_key:
                entry_key = _ability_loadout_key(ability_id, item.get("value")) or str(
                    ability_id
                )
            payload[key][str(entry_key)] = max(default_count, 0)

    passive_entries = passive_items if passive_items is not None else _passive_entries(unit)
    for entry in passive_entries:
        slug = entry.get("slug")
        if not slug:
            continue
        is_mandatory = bool(entry.get("is_mandatory", False))
        payload["passive"][str(slug)] = 1 if (entry.get("is_default") or is_mandatory) else 0

    return payload


def _extract_label_map(source: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(source, dict):
        items = source.items()
    elif isinstance(source, list):
        items = []
        for entry in source:
            if not isinstance(entry, dict):
                continue
            entry_id = (
                entry.get("loadout_key")
                or entry.get("key")
                or entry.get("id")
                or entry.get("ability_id")
            )
            if entry_id is None and entry.get("ability_id") is not None:
                entry_id = _ability_loadout_key(entry.get("ability_id"), entry.get("value"))
            if entry_id is None:
                continue
            name_value = entry.get("name") or entry.get("label") or entry.get("value")
            items.append((entry_id, name_value))
    else:
        return result
    for raw_id, raw_value in items:
        if raw_id is None or raw_value is None:
            continue
        text_value = str(raw_value).strip()
        if not text_value:
            continue
        result[str(raw_id)] = text_value[:ABILITY_NAME_MAX_LENGTH]
    return result


def _parse_loadout_json(text: str | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "weapons": {},
        "active": {},
        "aura": {},
        "passive": {},
        "active_labels": {},
        "aura_labels": {},
    }
    mode: str | None = None
    if not text:
        return base
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return base
    if isinstance(data, dict):
        mode_value = data.get("mode")
        if isinstance(mode_value, str):
            mode = mode_value
        items = data.items()
    else:
        return base
    for section, values in items:
        if section == "mode":
            continue
        if section in {"active_labels", "aura_labels"}:
            base[section] = _extract_label_map(values)
            continue
        if section not in {"weapons", "active", "aura", "passive"}:
            continue
        if isinstance(values, dict):
            iterable = values.items()
        elif isinstance(values, list):
            iterable = []
            for entry in values:
                if not isinstance(entry, dict):
                    continue
                if section == "passive":
                    entry_id = (
                        entry.get("slug")
                        or entry.get("id")
                        or entry.get("ability_id")
                        or entry.get("weapon_id")
                    )
                    if entry_id is None:
                        continue
                    raw_enabled = entry.get("enabled")
                    if raw_enabled is None:
                        raw_enabled = entry.get("count") or entry.get("per_model") or entry.get("value")

                    def _to_flag(value: Any) -> int:
                        if isinstance(value, bool):
                            return 1 if value else 0
                        if isinstance(value, (int, float)):
                            return 1 if value > 0 else 0
                        if value is None:
                            return 0
                        text = str(value).strip().lower()
                        if text in {"", "0", "false", "no", "nie"}:
                            return 0
                        return 1

                    iterable.append((entry_id, _to_flag(raw_enabled)))
                else:
                    entry_id = entry.get("id") or entry.get("weapon_id") or entry.get("ability_id")
                    if entry_id is None:
                        continue
                    iterable.append((entry_id, entry.get("per_model") or entry.get("count") or 0))
        else:
            continue
        section_payload: dict[str, int] = {}
        for raw_id, raw_count in iterable:
            key = str(raw_id)
            try:
                count_value = int(raw_count)
            except (TypeError, ValueError):
                try:
                    count_value = int(float(raw_count))
                except (TypeError, ValueError):
                    count_value = 0
            if count_value < 0:
                count_value = 0
            section_payload[key] = count_value
        base[section] = section_payload
    if mode:
        base["mode"] = mode
    return base


def _sanitize_loadout(
    unit: models.Unit,
    model_count: int,
    payload: dict[str, Any] | None,
    *,
    weapon_options: list[dict] | None = None,
    active_items: list[dict] | None = None,
    aura_items: list[dict] | None = None,
    passive_items: list[dict] | None = None,
) -> dict[str, Any]:
    resolved_passive_items = (
        passive_items if passive_items is not None else _passive_entries(unit)
    )
    defaults = _default_loadout_payload(
        unit,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=resolved_passive_items,
    )
    mode_value: str | None = None
    if isinstance(payload, dict):
        raw_mode = payload.get("mode")
        if isinstance(raw_mode, str):
            mode_value = raw_mode
    if not payload:
        return defaults
    safe_payload = {
        "weapons": payload.get("weapons") or {},
        "active": payload.get("active") or {},
        "aura": payload.get("aura") or {},
        "passive": payload.get("passive") or {},
        "active_labels": payload.get("active_labels") or {},
        "aura_labels": payload.get("aura_labels") or {},
    }

    max_count = max(int(model_count), 0)

    ability_sections: dict[str, list[dict]] = {
        "active": active_items if active_items is not None else _ability_entries(unit, "active"),
        "aura": aura_items if aura_items is not None else _ability_entries(unit, "aura"),
    }
    ability_id_lookup: dict[str, dict[str, list[str]]] = {}
    ability_label_lookup: dict[str, dict[str, str]] = {}
    for section_name, entries in ability_sections.items():
        id_map: dict[str, list[str]] = {}
        label_map: dict[str, str] = {}
        for entry in entries:
            ability_id = entry.get("ability_id")
            if ability_id is None:
                continue
            loadout_key = entry.get("loadout_key")
            if not loadout_key:
                loadout_key = _ability_loadout_key(ability_id, entry.get("value"))
            if not loadout_key:
                continue
            ability_id_str = str(ability_id)
            id_map.setdefault(ability_id_str, []).append(loadout_key)
            label = entry.get("label")
            if isinstance(label, str):
                normalized_label = label.strip()
                if normalized_label:
                    label_map[loadout_key] = normalized_label
        ability_id_lookup[section_name] = id_map
        ability_label_lookup[section_name] = label_map

    label_sources: dict[str, dict[str, str]] = {
        section: _extract_label_map(safe_payload.get(f"{section}_labels"))
        for section in ("active", "aura")
    }
    normalized_label_maps: dict[str, dict[str, str]] = {section: {} for section in label_sources}

    def _canonical_ability_key(
        section: str, key: str, label_hint: str | None = None
    ) -> str:
        key_str = str(key)
        if section not in ability_sections:
            return key_str
        defaults_section = defaults.get(section, {})
        if key_str in defaults_section:
            return key_str
        normalized_hint = label_hint.strip().casefold() if isinstance(label_hint, str) else None
        if normalized_hint:
            for candidate_key, candidate_label in ability_label_lookup.get(section, {}).items():
                candidate_normalized = candidate_label.strip().casefold()
                if candidate_normalized == normalized_hint:
                    return candidate_key
        base_id, _ = _split_ability_loadout_key(key_str)
        candidates = ability_id_lookup.get(section, {}).get(base_id, [])
        if len(candidates) == 1:
            return candidates[0]
        for candidate in candidates:
            if candidate in defaults_section:
                return candidate
        if candidates:
            return candidates[0]
        return key_str

    def _normalize_section(section: str) -> dict[str, Any]:
        source = safe_payload.get(section, {})
        if isinstance(source, dict):
            return {str(key): value for key, value in source.items() if key is not None}
        if isinstance(source, list):
            normalized: dict[str, Any] = {}
            for entry in source:
                if not isinstance(entry, dict):
                    continue
                if section == "passive":
                    entry_id = (
                        entry.get("slug")
                        or entry.get("id")
                        or entry.get("ability_id")
                        or entry.get("weapon_id")
                    )
                    raw_value = entry.get("enabled")
                    if raw_value is None:
                        raw_value = (
                            entry.get("count")
                            or entry.get("per_model")
                            or entry.get("value")
                        )
                else:
                    entry_id = entry.get("id") or entry.get("weapon_id") or entry.get("ability_id")
                    raw_value = entry.get("per_model") or entry.get("count") or entry.get("value")
                if entry_id is None:
                    continue
                normalized[str(entry_id)] = raw_value
            return normalized
        return {}

    def _merge(section: str, clamp: int | None = None) -> None:
        defaults_section = defaults.get(section, {})
        if not isinstance(defaults_section, dict):
            defaults_section = {}
            defaults[section] = defaults_section
        incoming_map = _normalize_section(section)
        if section in ability_sections:
            labels = label_sources.get(section, {})
            normalized_incoming: dict[str, Any] = {}
            for raw_key, raw_value in incoming_map.items():
                label_hint = labels.pop(raw_key, None)
                canonical_key = _canonical_ability_key(section, raw_key, label_hint)
                normalized_incoming[canonical_key] = raw_value
                if label_hint:
                    normalized_label_maps.setdefault(section, {})[canonical_key] = label_hint
            for raw_key, label_hint in list(labels.items()):
                canonical_key = _canonical_ability_key(section, raw_key, label_hint)
                normalized_label_maps.setdefault(section, {})[canonical_key] = label_hint
                labels.pop(raw_key, None)
            incoming_map = normalized_incoming
        else:
            existing_labels = label_sources.get(section, {})
            for key_str, value in existing_labels.items():
                normalized_label_maps.setdefault(section, {})[key_str] = value
        keys = set(defaults_section.keys()) | set(incoming_map.keys())
        for key in keys:
            key_str = str(key)
            raw_value = incoming_map.get(key_str, defaults_section.get(key_str, 0))
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                try:
                    value = int(float(raw_value))
                except (TypeError, ValueError):
                    value = defaults_section.get(key_str, 0)
            if value < 0:
                value = 0
            if section == "weapons":
                defaults_section[key_str] = value
            else:
                if clamp is None:
                    defaults_section[key_str] = min(value, max_count)
                elif clamp == 1:
                    defaults_section[key_str] = 1 if value > 0 else 0
                else:
                    defaults_section[key_str] = min(value, clamp)

    _merge("weapons")
    _merge("active")
    _merge("aura")
    _merge("passive", clamp=1)

    passive_defaults = defaults.get("passive")
    if not isinstance(passive_defaults, dict):
        passive_defaults = {}
        defaults["passive"] = passive_defaults
    for entry in resolved_passive_items:
        if not entry:
            continue
        slug_value = str(entry.get("slug") or "").strip()
        if not slug_value:
            continue
        if not entry.get("is_mandatory"):
            continue
        passive_defaults[slug_value] = 1

    for section in ("active", "aura"):
        defaults[f"{section}_labels"] = normalized_label_maps.get(section, {})

    if mode_value:
        defaults["mode"] = mode_value
    return defaults


def _roster_unit_loadout(
    roster_unit: models.RosterUnit,
    *,
    weapon_options: list[dict] | None = None,
    active_items: list[dict] | None = None,
    aura_items: list[dict] | None = None,
    passive_items: list[dict] | None = None,
) -> dict[str, Any]:
    raw_payload = _parse_loadout_json(roster_unit.extra_weapons_json)
    loadout = _sanitize_loadout(
        roster_unit.unit,
        roster_unit.count,
        raw_payload,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )

    return loadout


def _loadout_display_summary(
    roster_unit: models.RosterUnit,
    loadout: dict[str, dict[str, int]],
    weapon_options: list[dict],
) -> str:
    summary: list[str] = []
    mode = loadout.get("mode") if isinstance(loadout, dict) else None
    option_by_id = {str(option.get("id")): option for option in weapon_options if option.get("id") is not None}
    for weapon_id, stored_count in loadout.get("weapons", {}).items():
        option = option_by_id.get(weapon_id)
        if not option:
            continue
        try:
            parsed_count = int(stored_count)
        except (TypeError, ValueError):
            try:
                parsed_count = int(float(stored_count))
            except (TypeError, ValueError):
                parsed_count = 0
        if parsed_count < 0:
            parsed_count = 0
        if mode == "total":
            total_count = parsed_count
        else:
            total_count = parsed_count * max(int(roster_unit.count), 0)
        if total_count <= 0:
            continue
        name = option.get("name") or "Broń"
        summary.append(f"{name} x{total_count}")
    return ", ".join(summary)


def _classification_from_totals(
    warrior: float,
    shooter: float,
    available_slugs: set[str] | None = None,
) -> dict[str, Any] | None:
    warrior = max(float(warrior or 0.0), 0.0)
    shooter = max(float(shooter or 0.0), 0.0)
    if warrior <= 0 and shooter <= 0:
        return None

    pool = {slug for slug in available_slugs or set() if slug in {"wojownik", "strzelec"}}
    preferred: str | None = None
    if warrior > shooter:
        preferred = "wojownik"
    elif shooter > warrior:
        preferred = "strzelec"
    elif not pool:
        # Without any explicit role traits on the unit we can't resolve a tie
        # between the two role totals in a deterministic way.
        return None

    slug: str | None = None
    if pool:
        if preferred and preferred in pool:
            slug = preferred
        elif len(pool) == 1:
            slug = next(iter(pool))
        elif preferred and preferred not in pool:
            slug = next(iter(pool - {preferred}), None)
        elif preferred is None:
          
            slug = (
                "wojownik"
                if "wojownik" in pool
                else ("strzelec" if "strzelec" in pool else next(iter(pool), None))
            )
    else:
        slug = preferred

    if slug is None and pool:
        if "strzelec" in pool:
            slug = "strzelec"
        elif "wojownik" in pool:
            slug = "wojownik"
        else:
            slug = next(iter(pool), None)

    if not slug:
        return None

    selected_label = "Wojownik" if slug == "wojownik" else "Strzelec"
    warrior_points = round(warrior, 2)
    shooter_points = round(shooter, 2)
    display = f"Wojownik {warrior_points} pkt / Strzelec {shooter_points} pkt"
    return {
        "slug": slug,
        "label": selected_label,
        "warrior_cost": warrior_points,
        "shooter_cost": shooter_points,
        "display": display,
    }


def _roster_unit_classification(
    roster_unit: models.RosterUnit,
    loadout: dict[str, dict[str, int]] | None,
    *,
    totals: Mapping[str, float] | None = None,
) -> dict[str, Any] | None:
    totals_map: Mapping[str, float]
    if isinstance(totals, Mapping):
        totals_map = totals
    else:
        totals_map = costs.roster_unit_role_totals(roster_unit, loadout)
    warrior_total = float(totals_map.get("wojownik") or 0.0)
    shooter_total = float(totals_map.get("strzelec") or 0.0)
    available_slugs: set[str] = set()
    unit = getattr(roster_unit, "unit", None)
    if unit is not None:
        flags = utils.parse_flags(getattr(unit, "flags", None))
        traits = costs.flags_to_ability_list(flags)
        available_slugs = {
            costs.ability_identifier(trait) for trait in traits
        }
    return _classification_from_totals(warrior_total, shooter_total, available_slugs)


def _loadout_weapon_details(
    roster_unit: models.RosterUnit,
    loadout: dict[str, dict[str, int]],
    weapon_options: list[dict],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    mode = loadout.get("mode") if isinstance(loadout, dict) else None
    option_by_id = {
        str(option.get("id")): option
        for option in weapon_options
        if option.get("id") is not None
    }
    weapons_section = loadout.get("weapons") if isinstance(loadout, dict) else {}
    items = weapons_section.items() if isinstance(weapons_section, dict) else []
    for weapon_id, stored_count in items:
        option = option_by_id.get(str(weapon_id))
        if not option:
            continue
        try:
            parsed_count = int(stored_count)
        except (TypeError, ValueError):
            try:
                parsed_count = int(float(stored_count))
            except (TypeError, ValueError):
                parsed_count = 0
        if parsed_count < 0:
            parsed_count = 0
        if mode == "total":
            total_count = parsed_count
        else:
            total_count = parsed_count * max(int(roster_unit.count), 0)
        if total_count <= 0:
            continue
        details.append(
            {
                "name": option.get("name") or "Broń",
                "count": total_count,
                "range": option.get("range"),
                "attacks": option.get("attacks"),
                "ap": option.get("ap"),
                "traits": option.get("traits"),
            }
        )
    return details


def _roster_unit_export_data(
    roster_unit: models.RosterUnit,
    *,
    unit_cache: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unit = roster_unit.unit
    if unit is None:  # pragma: no cover - defensive fallback
        total_value = float(roster_unit.cached_cost or 0.0)
        rounded_total = utils.round_points(total_value)
        return {
            "instance": roster_unit,
            "unit": None,
            "unit_name": "Jednostka",
            "custom_name": (roster_unit.custom_name or "").strip() or None,
            "count": roster_unit.count,
            "quality": "-",
            "defense": "-",
            "toughness": "-",
            "passive_labels": [],
            "active_labels": [],
            "aura_labels": [],
            "weapon_details": [],
            "weapon_summary": "",
            "default_summary": "",
            "total_cost": total_value,
            "rounded_total_cost": rounded_total,
        }

    cache_key: int | None = getattr(unit, "id", None)
    cached_values: dict[str, Any] | None = None
    if unit_cache is not None and cache_key is not None:
        cached_values = unit_cache.get(cache_key)

    if cached_values is not None:
        weapon_options = cached_values.get("weapon_options")
        passive_items = cached_values.get("passive_items")
        active_items = cached_values.get("active_items")
        aura_items = cached_values.get("aura_items")
        default_summary = cached_values.get("default_summary")
        if weapon_options is None:
            weapon_options = _unit_weapon_options(unit)
        if passive_items is None:
            passive_items = _passive_entries(unit)
        if active_items is None:
            active_items = _ability_entries(unit, "active")
        if aura_items is None:
            aura_items = _ability_entries(unit, "aura")
        if default_summary is None:
            default_summary = _default_loadout_summary(unit)
            cached_values["default_summary"] = default_summary
    else:
        weapon_options = _unit_weapon_options(unit)
        passive_items = _passive_entries(unit)
        active_items = _ability_entries(unit, "active")
        aura_items = _ability_entries(unit, "aura")
        default_summary = _default_loadout_summary(unit)
        if unit_cache is not None and cache_key is not None:
            unit_cache[cache_key] = {
                "weapon_options": weapon_options,
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "default_summary": default_summary,
            }
    loadout = _roster_unit_loadout(
        roster_unit,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )
    classification = _roster_unit_classification(roster_unit, loadout)
    weapon_details = _loadout_weapon_details(roster_unit, loadout, weapon_options)
    weapon_summary = _loadout_display_summary(roster_unit, loadout, weapon_options)
    if not weapon_summary:
        if default_summary:
            weapon_summary = default_summary
        else:
            default_summary = _default_loadout_summary(unit)
            weapon_summary = default_summary
            if cached_values is not None:
                cached_values["default_summary"] = default_summary
            elif unit_cache is not None and cache_key is not None:
                unit_cache.setdefault(cache_key, {})["default_summary"] = default_summary
    selected_passives = _selected_passive_entries(
        roster_unit, loadout, passive_items, classification
    )
    selected_actives = _selected_ability_entries(loadout, active_items, "active")
    selected_auras = _selected_ability_entries(loadout, aura_items, "aura")
    passive_labels = [
        entry.get("label") or entry.get("raw") or entry.get("slug") or ""
        for entry in selected_passives
        if entry
    ]
    active_labels = [
        _ability_label_with_count(entry)
        for entry in selected_actives
        if entry
    ]
    aura_labels = [
        _ability_label_with_count(entry)
        for entry in selected_auras
        if entry
    ]
    total_value = float(roster_unit.cached_cost or costs.roster_unit_cost(roster_unit))
    rounded_total = utils.round_points(total_value)

    active_slugs: list[str] = []
    for entry in selected_actives:
        slug_value = entry.get("slug") if isinstance(entry, dict) else None
        identifier = costs.ability_identifier(slug_value) if slug_value else None
        if identifier:
            active_slugs.append(identifier)

    if default_summary is None:
        default_summary = _default_loadout_summary(unit)
        if cached_values is not None:
            cached_values["default_summary"] = default_summary
        elif unit_cache is not None and cache_key is not None:
            unit_cache.setdefault(cache_key, {})["default_summary"] = default_summary

    return {
        "instance": roster_unit,
        "unit": unit,
        "unit_name": unit.name,
        "custom_name": (roster_unit.custom_name or "").strip() or None,
        "count": roster_unit.count,
        "quality": unit.quality,
        "defense": unit.defense,
        "toughness": unit.toughness,
        "passive_labels": [label for label in passive_labels if label],
        "active_labels": [label for label in active_labels if label],
        "aura_labels": [label for label in aura_labels if label],
        "weapon_details": weapon_details,
        "weapon_summary": weapon_summary,
        "default_summary": default_summary,
        "total_cost": total_value,
        "rounded_total_cost": rounded_total,
        "classification": classification,
        "active_slugs": active_slugs,
    }


def _selected_passive_labels(
    roster_unit: models.RosterUnit,
    loadout: dict[str, dict[str, int]],
    passive_items: list[dict],
    classification: dict[str, Any] | None = None,
) -> list[str]:
    selected_entries = _selected_passive_entries(
        roster_unit, loadout, passive_items, classification
    )
    return [
        entry.get("label") or entry.get("raw") or entry.get("slug") or ""
        for entry in selected_entries
        if entry
    ]
