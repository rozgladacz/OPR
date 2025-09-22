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

router = APIRouter(prefix="/armory", tags=["armory"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def list_weapons(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapons = db.execute(select(models.Weapon).order_by(models.Weapon.name)).scalars().all()
    mine, global_items = utils.split_owned(weapons, current_user)
    return templates.TemplateResponse(
        "armory_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
        },
    )


def _ensure_access(weapon: models.Weapon, user: models.User | None) -> None:
    if weapon.owner_id is None and user is None:
        return
    if user is None:
        raise HTTPException(status_code=403, detail="Wymagane logowanie")
    if not user.is_admin and weapon.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak uprawnień do edycji")


@router.get("/new", response_class=HTMLResponse)
def new_weapon_form(
    request: Request,
    current_user: models.User | None = Depends(get_current_user(optional=True)),
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
    attacks: float = Form(1.0),
    ap: int = Form(0),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapon = models.Weapon(
        name=name,
        range=range,
        attacks=attacks,
        ap=ap,
        tags=tags,
        notes=notes,
        owner_id=current_user.id if current_user else None,
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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_access(weapon, current_user)
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
    attacks: float = Form(1.0),
    ap: int = Form(0),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_access(weapon, current_user)

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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_access(weapon, current_user)
    db.delete(weapon)
    db.commit()
    return RedirectResponse(url="/armory", status_code=303)
