from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs, utils

router = APIRouter(prefix="/rosters", tags=["rosters"])
templates = Jinja2Templates(directory="app/templates")


def _ensure_roster_access(roster: models.Roster, user: models.User | None) -> None:
    if roster.owner_id is None and user is None:
        return
    if user is None:
        raise HTTPException(status_code=403, detail="Wymagane logowanie")
    if not user.is_admin and roster.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do rozpiski")


def _load_upgrade_data(roster_unit: models.RosterUnit) -> dict:
    if not roster_unit.extra_weapons_json:
        return {"weapon_upgrades": [], "ability_upgrades": []}
    try:
        data = json.loads(roster_unit.extra_weapons_json)
    except (TypeError, json.JSONDecodeError):
        return {"weapon_upgrades": [], "ability_upgrades": []}
    data.setdefault("weapon_upgrades", [])
    data.setdefault("ability_upgrades", [])
    return data


@router.get("", response_class=HTMLResponse)
def list_rosters(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    rosters = db.execute(select(models.Roster).order_by(models.Roster.created_at.desc())).scalars().all()
    for roster in rosters:
        costs.update_cached_costs(roster.roster_units)
    mine, global_items = utils.split_owned(rosters, current_user)
    return templates.TemplateResponse(
        "rosters_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_roster_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    armies = db.execute(select(models.Army).order_by(models.Army.name)).scalars().all()
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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    limit_value = int(points_limit) if points_limit else None
    roster = models.Roster(
        name=name,
        army=army,
        points_limit=limit_value,
        owner_id=current_user.id if current_user else None,
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
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    available_units = (
        db.execute(select(models.Unit).where(models.Unit.army_id == roster.army_id).order_by(models.Unit.name))
        .scalars()
        .all()
    )
    available_unit_rows = [
        {
            "unit": unit,
            "cost": costs.unit_total_cost(unit),
            "weapon_name": unit.default_weapon.name if unit.default_weapon else "-",
        }
        for unit in available_units
    ]
    weapons = db.execute(select(models.Weapon).order_by(models.Weapon.name)).scalars().all()
    ability_choices = costs.ability_upgrade_choices()
    roster_entries = []
    for roster_unit in roster.roster_units:
        base_weapon = roster_unit.selected_weapon or roster_unit.unit.default_weapon
        weapon_options = []
        unit_size = max(roster_unit.count, 1)
        for weapon in weapons:
            delta = costs.per_model_weapon_delta(roster_unit.unit, base_weapon, weapon)
            weapon_options.append(
                {
                    "id": weapon.id,
                    "name": weapon.name,
                    "delta": delta,
                    "unit_delta": round(delta * unit_size, 2),
                }
            )
        weapon_options.sort(key=lambda item: item["name"].lower())
        ability_options = []
        for option in ability_choices:
            delta = costs.per_model_ability_delta(roster_unit.unit, option.value)
            ability_options.append(
                {
                    "value": option.value,
                    "label": option.label,
                    "delta": delta,
                    "unit_delta": round(delta * unit_size, 2),
                }
            )
        ability_options.sort(key=lambda item: item["label"].lower())
        upgrades = _load_upgrade_data(roster_unit)
        roster_entries.append(
            {
                "instance": roster_unit,
                "base_weapon": base_weapon,
                "weapon_options": weapon_options,
                "ability_options": ability_options,
                "upgrades": upgrades,
            }
        )
    total_cost = costs.roster_total(roster)

    return templates.TemplateResponse(
        "roster_edit.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "available_units": available_unit_rows,
            "weapons": weapons,
            "roster_entries": roster_entries,
            "total_cost": total_cost,
            "error": None,
        },
    )


@router.post("/{roster_id}/update")
def update_roster(
    roster_id: int,
    name: str = Form(...),
    points_limit: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)
    roster.name = name
    roster.points_limit = int(points_limit) if points_limit else None
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/add")
def add_roster_unit(
    roster_id: int,
    unit_id: int = Form(...),
    count: int = Form(1),
    selected_weapon_id: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    unit = db.get(models.Unit, unit_id)
    if not roster or not unit or unit.army_id != roster.army_id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    weapon_id = int(selected_weapon_id) if selected_weapon_id else None
    weapon = db.get(models.Weapon, weapon_id) if weapon_id else None
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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    roster_unit.count = count
    roster_unit.selected_weapon_id = int(selected_weapon_id) if selected_weapon_id else None
    roster_unit.cached_cost = costs.roster_unit_cost(roster_unit)
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/{roster_unit_id}/weapons/add")
def add_roster_weapon_upgrade(
    roster_id: int,
    roster_unit_id: int,
    weapon_id: int = Form(...),
    count: int = Form(1),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)

    base_weapon = roster_unit.selected_weapon or roster_unit.unit.default_weapon
    delta_per_model = costs.per_model_weapon_delta(roster_unit.unit, base_weapon, weapon)
    applied_count = max(1, min(count, roster_unit.count))
    upgrades = _load_upgrade_data(roster_unit)
    upgrades["weapon_upgrades"].append(
        {
            "weapon_id": weapon.id,
            "name": weapon.name,
            "count": applied_count,
            "per_model_delta": delta_per_model,
            "delta": round(delta_per_model * applied_count, 2),
        }
    )
    roster_unit.extra_weapons_json = json.dumps(upgrades, ensure_ascii=False)
    costs.update_cached_costs([roster_unit])
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/{roster_unit_id}/abilities/add")
def add_roster_ability_upgrade(
    roster_id: int,
    roster_unit_id: int,
    ability: str = Form(...),
    count: int = Form(1),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    ability_map = {option.value: option.label for option in costs.ability_upgrade_choices()}
    if ability not in ability_map:
        raise HTTPException(status_code=400, detail="Nieznana zdolność dodatkowa")

    delta_per_model = costs.per_model_ability_delta(roster_unit.unit, ability)
    applied_count = max(1, min(count, roster_unit.count))
    upgrades = _load_upgrade_data(roster_unit)
    upgrades["ability_upgrades"].append(
        {
            "value": ability,
            "ability": ability_map[ability],
            "count": applied_count,
            "per_model_delta": delta_per_model,
            "delta": round(delta_per_model * applied_count, 2),
        }
    )
    roster_unit.extra_weapons_json = json.dumps(upgrades, ensure_ascii=False)
    costs.update_cached_costs([roster_unit])
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/{roster_unit_id}/upgrades/remove")
def remove_roster_upgrade(
    roster_id: int,
    roster_unit_id: int,
    kind: str = Form(...),
    index: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    upgrades = _load_upgrade_data(roster_unit)
    try:
        if kind == "weapon":
            upgrades["weapon_upgrades"].pop(index)
        elif kind == "ability":
            upgrades["ability_upgrades"].pop(index)
        else:
            raise KeyError
    except (IndexError, KeyError):
        raise HTTPException(status_code=400, detail="Nieprawidłowa pozycja do usunięcia")

    roster_unit.extra_weapons_json = json.dumps(upgrades, ensure_ascii=False)
    costs.update_cached_costs([roster_unit])
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)


@router.post("/{roster_id}/units/{roster_unit_id}/delete")
def delete_roster_unit(
    roster_id: int,
    roster_unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    roster_unit = db.get(models.RosterUnit, roster_unit_id)
    if not roster or not roster_unit or roster_unit.roster_id != roster.id:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    db.delete(roster_unit)
    db.commit()
    return RedirectResponse(url=f"/rosters/{roster.id}", status_code=303)
