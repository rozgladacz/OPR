from __future__ import annotations

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
    weapons = db.execute(select(models.Weapon).order_by(models.Weapon.name)).scalars().all()
    total_cost = costs.roster_total(roster)

    return templates.TemplateResponse(
        "roster_edit.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "available_units": available_units,
            "weapons": weapons,
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
