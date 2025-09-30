from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs, utils
from ..services.rules import collect_roster_warnings

router = APIRouter(prefix="/rosters", tags=["rosters"])
templates = Jinja2Templates(directory="app/templates")


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


@router.get("", response_class=HTMLResponse)
def list_rosters(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = select(models.Roster).order_by(models.Roster.created_at.desc())
    if not current_user.is_admin:
        query = query.where(
            or_(
                models.Roster.owner_id == current_user.id,
                models.Roster.owner_id.is_(None),
            )
        )
    rosters = db.execute(query).scalars().all()
    for roster in rosters:
        costs.update_cached_costs(roster.roster_units)
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
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    selected_id = request.query_params.get("selected")

    costs.update_cached_costs(roster.roster_units)
    available_units = (
        db.execute(select(models.Unit).where(models.Unit.army_id == roster.army_id).order_by(models.Unit.name))
        .scalars()
        .all()
    )
    available_unit_options = []
    for unit in available_units:
        weapon_options = _unit_weapon_options(unit)
        passive_items = _passive_entries(unit)
        active_items = _ability_entries(unit, "active")
        aura_items = _ability_entries(unit, "aura")
        available_unit_options.append(
            {
                "unit": unit,
                "weapon_options": weapon_options,
                "default_summary": _default_loadout_summary(unit),
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "unit_cost": costs.unit_total_cost(unit),
            }
        )

    roster_items = []
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        weapon_options = _unit_weapon_options(unit)
        passive_items = _passive_entries(unit)
        active_items = _ability_entries(unit, "active")
        aura_items = _ability_entries(unit, "aura")
        loadout = _roster_unit_loadout(
            roster_unit,
            weapon_options=weapon_options,
            active_items=active_items,
            aura_items=aura_items,
            passive_items=passive_items,
        )
        classification = _roster_unit_classification(roster_unit, loadout)
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
                "default_summary": _default_loadout_summary(unit),
                "weapon_options": weapon_options,
                "loadout": loadout,
                "loadout_summary": _loadout_display_summary(roster_unit, loadout, weapon_options),
                "base_cost_per_model": _base_cost_per_model(unit, classification),
                "classification": classification,
            }
        )
    total_cost = costs.roster_total(roster)
    warnings = collect_roster_warnings(roster)
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
            "total_cost": total_cost,
            "error": None,
            "can_edit": can_edit,
            "can_delete": can_delete,
            "warnings": warnings,
            "selected_id": selected_id,
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
    unit_id: int = Form(...),
    count: int = Form(1),
    selected_weapon_id: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    unit = db.get(models.Unit, unit_id)
    if not roster or not unit or unit.army_id != roster.army_id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    allowed_weapon_ids = _unit_allowed_weapon_ids(unit)
    weapon_id = int(selected_weapon_id) if selected_weapon_id else None
    weapon = db.get(models.Weapon, weapon_id) if weapon_id else None
    if weapon_id and weapon_id not in allowed_weapon_ids:
        weapon = None
    if weapon and weapon.armory_id != roster.army.armory_id:
        weapon = None
    if weapon and not current_user.is_admin and weapon.owner_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do broni")
    count = max(int(count), 1)
    weapon_options = _unit_weapon_options(unit)
    active_items = _ability_entries(unit, "active")
    aura_items = _ability_entries(unit, "aura")
    passive_items = _passive_entries(unit)
    loadout = _default_loadout_payload(
        unit,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )
    if weapon:
        selected_key = str(weapon.id)
        for key in list(loadout["weapons"].keys()):
            loadout["weapons"][key] = 1 if key == selected_key else 0
        if selected_key not in loadout["weapons"]:
            loadout["weapons"][selected_key] = 1

    roster_unit = models.RosterUnit(
        roster=roster,
        unit=unit,
        count=count,
        selected_weapon=weapon,
        extra_weapons_json=json.dumps(loadout, ensure_ascii=False),
    )
    roster_unit.cached_cost = costs.roster_unit_cost(roster_unit)
    db.add(roster_unit)
    db.commit()
    db.refresh(roster_unit)
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
    selected_weapon_id: str | None = Form(None),
    loadout_json: str | None = Form(None),
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    roster_unit.count = max(int(count), 1)
    weapon_options = _unit_weapon_options(roster_unit.unit)
    active_items = _ability_entries(roster_unit.unit, "active")
    aura_items = _ability_entries(roster_unit.unit, "aura")
    passive_items = _passive_entries(roster_unit.unit)

    parsed_loadout = _parse_loadout_json(loadout_json) if loadout_json is not None else None
    loadout = _sanitize_loadout(
        roster_unit.unit,
        roster_unit.count,
        parsed_loadout,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
    )

    classification = _roster_unit_classification(roster_unit, loadout)
    loadout = _apply_classification_to_loadout(loadout, classification) or loadout

    weapon_id: int | None = None
    if loadout_json is None:
        allowed_weapon_ids = _unit_allowed_weapon_ids(roster_unit.unit)
        weapon_id = int(selected_weapon_id) if selected_weapon_id else None
        if weapon_id:
            weapon = db.get(models.Weapon, weapon_id)
            if (
                not weapon
                or weapon.id not in allowed_weapon_ids
                or weapon.armory_id != roster.army.armory_id
            ):
                weapon_id = None
            elif not current_user.is_admin and weapon.owner_id not in (None, current_user.id):
                raise HTTPException(status_code=403, detail="Brak dostępu do broni")
        if weapon_id:
            selected_key = str(weapon_id)
            for key in list(loadout["weapons"].keys()):
                loadout["weapons"][key] = 1 if key == selected_key else 0
            if selected_key not in loadout["weapons"]:
                loadout["weapons"][selected_key] = 1
    roster_unit.selected_weapon_id = weapon_id
    roster_unit.custom_name = custom_name.strip() if custom_name else None
    roster_unit.extra_weapons_json = json.dumps(loadout, ensure_ascii=False)
    roster_unit.cached_cost = costs.roster_unit_cost(roster_unit)
    db.commit()
    accept_header = (request.headers.get("accept") or "").lower()
    if "application/json" in accept_header:
        total_cost = costs.roster_total(roster)
        classification = _roster_unit_classification(roster_unit, loadout)
        selected_passives = _selected_passive_entries(
            roster_unit, loadout, passive_items, classification
        )
        selected_actives = _selected_ability_entries(loadout, active_items, "active")
        selected_auras = _selected_ability_entries(loadout, aura_items, "aura")
        warnings = collect_roster_warnings(roster)
        return JSONResponse(
            {
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
        )
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
        selected_weapon_id=roster_unit.selected_weapon_id,
        extra_weapons_json=roster_unit.extra_weapons_json,
        custom_name=roster_unit.custom_name,
    )
    clone.cached_cost = costs.roster_unit_cost(clone)
    db.add(clone)
    db.commit()
    db.refresh(clone)
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

    db.delete(roster_unit)
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
        options.append(
            {
                "id": link.weapon_id,
                "name": link.weapon.effective_name,
                "is_default": bool(getattr(link, "is_default", False)),
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


def _unit_allowed_weapon_ids(unit: models.Unit) -> set[int]:
    options = _unit_weapon_options(unit)
    return {option["id"] for option in options}


def _passive_entries(unit: models.Unit) -> list[dict]:
    payload = utils.passive_flags_to_payload(unit.flags)
    entries: list[dict] = []
    flags = utils.parse_flags(unit.flags)
    unit_traits = costs.flags_to_ability_list(flags)
    hidden_slugs = {"wojownik", "strzelec"}
    for item in payload:
        if not item:
            continue
        slug = str(item.get("slug") or "").strip()
        if slug in hidden_slugs:
            continue
        label = item.get("label") or slug
        value = item.get("value")
        description = item.get("description") or ""
        is_default = bool(item.get("is_default", False))
        try:
            cost_value = float(
                costs.ability_cost_from_name(
                    label or slug,
                    value,
                    unit_traits,
                    toughness=unit.toughness,
                )
            )
        except Exception:  # pragma: no cover - fallback for unexpected input
            cost_value = float(
                costs.ability_cost_from_name(
                    slug,
                    value,
                    unit_traits,
                    toughness=unit.toughness,
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
                key = entry.get("id") or entry.get("ability_id")
            if key is None:
                continue
            items.append((key, entry.get("count")))
    else:
        return result
    for key, raw_value in items:
        if key is None:
            continue
        count = _coerce_int(raw_value, 0)
        if count < 0:
            count = 0
        result[str(key)] = count
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
        default_flag = 1 if entry.get("is_default") or entry.get("default_count") else 0
        selected_flag = flags.get(slug, default_flag)
        if selected_flag <= 0:
            seen_slugs.add(slug)
            if identifier:
                seen_identifiers.add(identifier)
            continue
        item = dict(entry)
        item["selected"] = True
        item["count"] = 1
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


def _apply_classification_to_loadout(
    loadout: dict[str, Any] | None,
    classification: dict[str, Any] | None,
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

    for key in list(passive_section.keys()):
        identifier = costs.ability_identifier(key)
        if identifier not in costs.ROLE_SLUGS:
            continue
        if target_identifier and identifier == target_identifier and target_key is None:
            target_key = str(key)
            passive_section[key] = 1
            continue
        passive_section.pop(key, None)

    if target_identifier:
        passive_section[str(target_key or target_identifier)] = 1

    return loadout


def _selected_ability_entries(
    loadout: dict[str, Any] | None,
    ability_items: list[dict] | None,
    section: str,
) -> list[dict]:
    entries = ability_items if ability_items is not None else []
    counts = _loadout_counts(loadout, section)
    selected: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry or entry.get("ability_id") is None:
            continue
        ability_id = entry.get("ability_id")
        key = str(ability_id)
        default_count = _coerce_int(entry.get("default_count") or 0, 0)
        stored = counts.get(key, default_count)
        if stored <= 0:
            seen.add(key)
            continue
        item = dict(entry)
        item["count"] = stored
        selected.append(item)
        seen.add(key)
    for key, value in counts.items():
        if key in seen or value <= 0:
            continue
        selected.append({
            "ability_id": key,
            "label": str(key),
            "description": "",
            "count": value,
        })
    return selected


def _ability_label_with_count(entry: dict) -> str:
    label = entry.get("label") or entry.get("raw") or entry.get("slug") or ""
    count = _coerce_int(entry.get("count"), 0)
    if count > 1:
        return f"{label} ×{count}"
    return label


def _ability_entries(unit: models.Unit, ability_type: str) -> list[dict]:
    entries: list[dict] = []
    payload = ability_registry.unit_ability_payload(unit, ability_type)
    payload_by_id = {
        item.get("ability_id"): item for item in payload if item.get("ability_id")
    }
    flags = utils.parse_flags(unit.flags)
    unit_traits = costs.flags_to_ability_list(flags)
    for link in getattr(unit, "abilities", []):
        ability = link.ability
        if not ability or ability.type != ability_type:
            continue
        payload_entry = payload_by_id.get(ability.id) or {}
        label = payload_entry.get("label") or ability.name or ""
        description = payload_entry.get("description") or ability.description or ""
        is_default = payload_entry.get("is_default")
        if is_default is None:
            is_default = False
            if link.params_json:
                try:
                    params = json.loads(link.params_json)
                except json.JSONDecodeError:
                    params = {}
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
                "label": label,
                "description": description,
                "cost": cost_value,
                "is_default": bool(is_default),
                "default_count": 1 if bool(is_default) else 0,
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
        label = entry.get("label") or slug_value
        value = entry.get("value")
        passive_cost += costs.ability_cost_from_name(
            label or slug_value,
            value,
            base_traits,
            toughness=unit.toughness,
        )
    return round(base_value + passive_cost, 2)


def _default_loadout_payload(
    unit: models.Unit,
    weapon_options: list[dict] | None = None,
    active_items: list[dict] | None = None,
    aura_items: list[dict] | None = None,
    passive_items: list[dict] | None = None,
) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {
        "weapons": {},
        "active": {},
        "aura": {},
        "passive": {},
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
            payload[key][str(ability_id)] = max(default_count, 0)

    passive_entries = passive_items if passive_items is not None else _passive_entries(unit)
    for entry in passive_entries:
        slug = entry.get("slug")
        if not slug:
            continue
        payload["passive"][str(slug)] = 1 if entry.get("is_default") else 0

    return payload


def _parse_loadout_json(text: str | None) -> dict[str, dict[str, int]]:
    base: dict[str, dict[str, int] | str] = {
        "weapons": {},
        "active": {},
        "aura": {},
        "passive": {},
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
        if section not in base:
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
    payload: dict[str, dict[str, int]] | None,
    *,
    weapon_options: list[dict] | None = None,
    active_items: list[dict] | None = None,
    aura_items: list[dict] | None = None,
    passive_items: list[dict] | None = None,
) -> dict[str, dict[str, int]]:
    defaults = _default_loadout_payload(
        unit,
        weapon_options=weapon_options,
        active_items=active_items,
        aura_items=aura_items,
        passive_items=passive_items,
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
    }

    max_count = max(int(model_count), 0)

    def _merge(section: str, clamp: int | None = None) -> None:
        defaults_section = defaults.get(section, {})
        incoming = safe_payload.get(section, {})
        for key in defaults_section.keys():
            raw_value = incoming.get(key, defaults_section[key])
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                try:
                    value = int(float(raw_value))
                except (TypeError, ValueError):
                    value = defaults_section[key]
            if value < 0:
                value = 0
            if section == "weapons":
                defaults_section[key] = value
            else:
                if clamp is None:
                    defaults_section[key] = min(value, max_count)
                elif clamp == 1:
                    defaults_section[key] = 1 if value > 0 else 0
                else:
                    defaults_section[key] = min(value, clamp)

    _merge("weapons")
    _merge("active")
    _merge("aura")
    _merge("passive", clamp=1)
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
) -> dict[str, dict[str, int]]:
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

    # Backwards compatibility for legacy rosters using selected_weapon_id.
    if (
        not roster_unit.extra_weapons_json
        and roster_unit.selected_weapon_id
        and str(roster_unit.selected_weapon_id) not in loadout["weapons"]
    ):
        loadout["weapons"][str(roster_unit.selected_weapon_id)] = 1

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

    slug: str | None = None
    if pool:
        if preferred and preferred in pool:
            slug = preferred
        elif len(pool) == 1:
            slug = next(iter(pool))
        elif preferred and preferred not in pool:
            slug = next(iter(pool - {preferred}), None)
        elif preferred is None:
            slug = "strzelec" if "strzelec" in pool else "wojownik"
    else:
        slug = preferred or "strzelec"

    if not slug:
        return None

    selected_label = "Wojownik" if slug == "wojownik" else "Strzelec"
    warrior_points = int(round(warrior))
    shooter_points = int(round(shooter))
    display = f"Wojownik {warrior_points} pkt / Strzelec {shooter_points} pkt"
    return {
        "slug": slug,
        "label": selected_label,
        "warrior_cost": round(warrior, 2),
        "shooter_cost": round(shooter, 2),
        "display": display,
    }


def _roster_unit_classification(
    roster_unit: models.RosterUnit,
    loadout: dict[str, dict[str, int]] | None,
) -> dict[str, Any] | None:
    totals = costs.roster_unit_role_totals(roster_unit, loadout)
    warrior_total = totals.get("wojownik", 0.0)
    shooter_total = totals.get("strzelec", 0.0)
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
    if not details:
        weapon = roster_unit.selected_weapon or roster_unit.unit.default_weapon
        if weapon:
            details.append(
                {
                    "name": weapon.effective_name or weapon.name or "Broń",
                    "count": max(int(roster_unit.count), 0),
                    "range": weapon.effective_range or weapon.range or "-",
                    "attacks": getattr(weapon, "display_attacks", None)
                    or weapon.effective_attacks,
                    "ap": weapon.effective_ap,
                    "traits": weapon.effective_tags or weapon.tags or "",
                }
            )
    return details


def _roster_unit_export_data(
    roster_unit: models.RosterUnit,
) -> dict[str, Any]:
    unit = roster_unit.unit
    if unit is None:  # pragma: no cover - defensive fallback
        total_value = float(roster_unit.cached_cost or 0.0)
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
        }

    weapon_options = _unit_weapon_options(unit)
    passive_items = _passive_entries(unit)
    active_items = _ability_entries(unit, "active")
    aura_items = _ability_entries(unit, "aura")
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
        weapon_summary = _default_loadout_summary(unit)
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
        "default_summary": _default_loadout_summary(unit),
        "total_cost": total_value,
        "classification": classification,
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
