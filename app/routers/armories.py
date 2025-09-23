from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs, utils

router = APIRouter(prefix="/armory", tags=["armory"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def list_weapons(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = select(models.Weapon).order_by(models.Weapon.name)
    if not current_user.is_admin:
        query = query.where(
            or_(
                models.Weapon.owner_id == current_user.id,
                models.Weapon.owner_id.is_(None),
            )
        )
    weapons = db.execute(query).scalars().all()
    updated = False
    for weapon in weapons:
        recalculated = costs.weapon_cost(weapon)
        if weapon.cached_cost is None or not math.isclose(weapon.cached_cost, recalculated, rel_tol=1e-9, abs_tol=1e-9):
            weapon.cached_cost = recalculated
            updated = True

    if updated:
        db.commit()

    mine, global_items, others = utils.split_owned(weapons, current_user)
    return templates.TemplateResponse(
        "armory_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
            "others": others,
        },
    )


def _ensure_edit_access(weapon: models.Weapon, user: models.User) -> None:
    if user.is_admin:
        return
    if weapon.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Brak uprawnień do edycji")


@router.get("/new", response_class=HTMLResponse)
def new_weapon_form(
    request: Request,
    current_user: models.User = Depends(get_current_user()),
):
    return templates.TemplateResponse(
        "armory_form.html",
        {"request": request, "user": current_user, "weapon": None, "error": None},
    )


@router.post("/new")
def create_weapon(
    request: Request,
    name: str = Form(...),
    range: str = Form(...),
    attacks: int = Form(1),
    ap: int = Form(0),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    weapon = models.Weapon(
        name=name,
        range=range,
        attacks=attacks,
        ap=ap,
        tags=tags,
        notes=notes,
        owner_id=current_user.id,
    )
    weapon.cached_cost = costs.weapon_cost(weapon)
    db.add(weapon)
    db.commit()
    return RedirectResponse(url="/armory", status_code=303)


@router.get("/{weapon_id}/edit", response_class=HTMLResponse)
def edit_weapon_form(
    weapon_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_edit_access(weapon, current_user)
    return templates.TemplateResponse(
        "armory_form.html",
        {"request": request, "user": current_user, "weapon": weapon, "error": None},
    )


@router.post("/{weapon_id}/edit")
def update_weapon(
    weapon_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(...),
    attacks: int = Form(1),
    ap: int = Form(0),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_edit_access(weapon, current_user)

    weapon.name = name
    weapon.range = range
    weapon.attacks = attacks
    weapon.ap = ap
    weapon.tags = tags
    weapon.notes = notes
    weapon.cached_cost = costs.weapon_cost(weapon)
    db.commit()
    return RedirectResponse(url="/armory", status_code=303)


@router.post("/{weapon_id}/delete")
def delete_weapon(
    weapon_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_edit_access(weapon, current_user)
    db.delete(weapon)
    db.commit()
    return RedirectResponse(url="/armory", status_code=303)
