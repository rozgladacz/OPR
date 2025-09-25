from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs, utils

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

    costs.update_cached_costs(roster.roster_units)
    available_units = (
        db.execute(select(models.Unit).where(models.Unit.army_id == roster.army_id).order_by(models.Unit.name))
        .scalars()
        .all()
    )
    available_unit_options = [
        {
            "unit": unit,
            "weapon_options": _unit_weapon_options(unit),
            "default_summary": _default_loadout_summary(unit),
            "passive_items": _passive_entries(unit),
            "active_items": _ability_entries(unit, "active"),
            "aura_items": _ability_entries(unit, "aura"),
        }
        for unit in available_units
    ]

    roster_items = []
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        passive_items = _passive_entries(unit)
        active_items = _ability_entries(unit, "active")
        aura_items = _ability_entries(unit, "aura")
        roster_items.append(
            {
                "instance": roster_unit,
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "default_summary": _default_loadout_summary(unit),
                "weapon_options": _unit_weapon_options(unit),
            }
        )
    total_cost = costs.roster_total(roster)
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
    roster_unit = models.RosterUnit(
        roster=roster,
        unit=unit,
        count=count,
        selected_weapon=weapon,
    )
    roster_unit.cached_cost = costs.roster_unit_cost(roster_unit)
    db.add(roster_unit)
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/{roster_unit_id}/update")
def update_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    count: int = Form(...),
    selected_weapon_id: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_edit_access(roster, current_user)

    roster_unit.count = max(int(count), 1)
    allowed_weapon_ids = _unit_allowed_weapon_ids(roster_unit.unit)
    weapon_id = int(selected_weapon_id) if selected_weapon_id else None
    if weapon_id:
        weapon = db.get(models.Weapon, weapon_id)
        if not weapon or weapon.id not in allowed_weapon_ids or weapon.armory_id != roster.army.armory_id:
            weapon_id = None
        elif not current_user.is_admin and weapon.owner_id not in (None, current_user.id):
            raise HTTPException(status_code=403, detail="Brak dostępu do broni")
    roster_unit.selected_weapon_id = weapon_id
    roster_unit.cached_cost = costs.roster_unit_cost(roster_unit)
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


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
    for item in payload:
        if not item:
            continue
        entries.append(
            {
                "label": item.get("label") or item.get("slug") or "",
                "description": item.get("description") or "",
                "cost": None,
                "is_default": bool(item.get("is_default", False)),
            }
        )
    return entries


def _passive_labels(unit: models.Unit) -> list[str]:
    return [
        entry["label"]
        for entry in _passive_entries(unit)
        if entry.get("label")
    ]


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
        cost_value = costs.ability_cost(link, unit_traits)
        entries.append(
            {
                "label": label,
                "description": description,
                "cost": cost_value,
                "is_default": bool(is_default),
            }
        )
    entries.sort(key=lambda entry: (not entry.get("is_default", False), entry.get("label", "").casefold()))
    return entries
