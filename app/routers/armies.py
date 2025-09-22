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

router = APIRouter(prefix="/armies", tags=["armies"])
templates = Jinja2Templates(directory="app/templates")


def _ensure_army_access(army: models.Army, user: models.User | None) -> None:
    if army.owner_id is None and user is None:
        return
    if user is None:
        raise HTTPException(status_code=403, detail="Wymagane logowanie")
    if not user.is_admin and army.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do armii")


@router.get("", response_class=HTMLResponse)
def list_armies(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    armies = db.execute(select(models.Army).order_by(models.Army.name)).scalars().all()
    mine, global_items = utils.split_owned(armies, current_user)
    return templates.TemplateResponse(
        "armies_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_army_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    rulesets = db.execute(select(models.RuleSet)).scalars().all()
    return templates.TemplateResponse(
        "army_form.html",
        {
            "request": request,
            "user": current_user,
            "rulesets": rulesets,
            "army": None,
            "error": None,
        },
    )


@router.post("/new")
def create_army(
    request: Request,
    name: str = Form(...),
    ruleset_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    ruleset = db.get(models.RuleSet, ruleset_id)
    if not ruleset:
        raise HTTPException(status_code=404)
    army = models.Army(name=name, ruleset=ruleset, owner_id=current_user.id if current_user else None)
    db.add(army)
    db.commit()
    return RedirectResponse(url=f"/armies/{army.id}", status_code=303)


@router.get("/{army_id}", response_class=HTMLResponse)
def view_army(
    army_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)

    weapons = db.execute(select(models.Weapon).order_by(models.Weapon.name)).scalars().all()
    rulesets = db.execute(select(models.RuleSet).order_by(models.RuleSet.name)).scalars().all()
    units = [
        {
            "instance": unit,
            "cost": costs.unit_total_cost(unit),
        }
        for unit in army.units
    ]
    return templates.TemplateResponse(
        "army_edit.html",
        {
            "request": request,
            "user": current_user,
            "army": army,
            "units": units,
            "weapons": weapons,
            "rulesets": rulesets,
            "error": None,
        },
    )


@router.post("/{army_id}/update")
def update_army(
    army_id: int,
    name: str = Form(...),
    ruleset_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)
    army.name = name
    army.ruleset_id = ruleset_id
    db.commit()
    return RedirectResponse(url=f"/armies/{army.id}", status_code=303)


@router.post("/{army_id}/units/new")
def add_unit(
    army_id: int,
    name: str = Form(...),
    quality: int = Form(...),
    defense: int = Form(...),
    toughness: int = Form(...),
    default_weapon_id: str | None = Form(None),
    flags: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)

    weapon_id = int(default_weapon_id) if default_weapon_id else None
    weapon = db.get(models.Weapon, weapon_id) if weapon_id else None
    unit = models.Unit(
        name=name,
        quality=quality,
        defense=defense,
        toughness=toughness,
        flags=flags,
        default_weapon=weapon,
        army=army,
        owner_id=current_user.id if current_user else None,
    )
    db.add(unit)
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)


@router.get("/{army_id}/units/{unit_id}/edit", response_class=HTMLResponse)
def edit_unit_form(
    army_id: int,
    unit_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)
    weapons = db.execute(select(models.Weapon).order_by(models.Weapon.name)).scalars().all()
    return templates.TemplateResponse(
        "unit_form.html",
        {
            "request": request,
            "user": current_user,
            "army": army,
            "unit": unit,
            "weapons": weapons,
            "error": None,
        },
    )


@router.post("/{army_id}/units/{unit_id}/edit")
def update_unit(
    army_id: int,
    unit_id: int,
    name: str = Form(...),
    quality: int = Form(...),
    defense: int = Form(...),
    toughness: int = Form(...),
    default_weapon_id: str | None = Form(None),
    flags: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)

    unit.name = name
    unit.quality = quality
    unit.defense = defense
    unit.toughness = toughness
    unit.flags = flags
    unit.default_weapon_id = int(default_weapon_id) if default_weapon_id else None
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)


@router.post("/{army_id}/units/{unit_id}/delete")
def delete_unit(
    army_id: int,
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_access(army, current_user)
    db.delete(unit)
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)
