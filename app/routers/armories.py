from __future__ import annotations

from types import SimpleNamespace

import unicodedata

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


def _available_weapon_tags(db: Session) -> list[str]:
    tags = set(costs.get_known_weapon_tags())
    existing = db.execute(select(models.Weapon.tags)).scalars().all()
    for entry in existing:
        for tag in costs.parse_weapon_tags(entry):
            if tag:
                tags.add(tag)
    return sorted(tags)


def _render_weapon_form(
    request: Request,
    user: models.User | None,
    available_tags: list[str],
    weapon: object | None,
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "armory_form.html",
        {
            "request": request,
            "user": user,
            "weapon": weapon,
            "available_tags": available_tags,
            "error": error,
        },
        status_code=status_code,
    )


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()


def _parse_tags(raw_tags: str | None) -> tuple[str | None, list[str]]:
    tags_list = costs.parse_weapon_tags(raw_tags)
    tags_text = ",".join(tags_list) if tags_list else None
    return tags_text, tags_list


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
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    available_tags = _available_weapon_tags(db)
    return _render_weapon_form(request, current_user, available_tags, weapon=None)


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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    available_tags = _available_weapon_tags(db)
    normalized_range = costs.normalize_range_value(range)
    if ap < -1 or ap > 5:
        weapon_data = SimpleNamespace(name=name, range=range, attacks=attacks, ap=ap, tags=tags, notes=notes)
        return _render_weapon_form(
            request,
            current_user,
            available_tags,
            weapon_data,
            error="AP musi mieścić się w zakresie od -1 do 5.",
            status_code=400,
        )
    if attacks < 0:
        weapon_data = SimpleNamespace(name=name, range=range, attacks=attacks, ap=ap, tags=tags, notes=notes)
        return _render_weapon_form(
            request,
            current_user,
            available_tags,
            weapon_data,
            error="Ataki muszą być liczbą całkowitą większą lub równą 0.",
            status_code=400,
        )

    tags_text, tags_list = _parse_tags(tags)
    allowed_normalized = {_normalize_token(tag) for tag in available_tags}
    invalid = [tag for tag in tags_list if _normalize_token(tag) not in allowed_normalized]
    if invalid:
        weapon_data = SimpleNamespace(name=name, range=range, attacks=attacks, ap=ap, tags=tags_text, notes=notes)
        error = "Nieznane tagi: " + ", ".join(invalid)
        return _render_weapon_form(request, current_user, available_tags, weapon_data, error=error, status_code=400)

    weapon = models.Weapon(
        name=name,
        range=normalized_range,
        attacks=attacks,
        ap=ap,
        tags=tags_text,
        notes=notes,
        owner_id=current_user.id if current_user else None,
    )
    weapon.cached_cost = costs.weapon_cost(weapon, quality=4)
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
    available_tags = _available_weapon_tags(db)
    return _render_weapon_form(request, current_user, available_tags, weapon=weapon)


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
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon:
        raise HTTPException(status_code=404)
    _ensure_access(weapon, current_user)
    available_tags = _available_weapon_tags(db)
    normalized_range = costs.normalize_range_value(range)
    if ap < -1 or ap > 5:
        temp = SimpleNamespace(
            id=weapon.id,
            name=name,
            range=range,
            attacks=attacks,
            ap=ap,
            tags=tags,
            notes=notes,
        )
        return _render_weapon_form(
            request,
            current_user,
            available_tags,
            temp,
            error="AP musi mieścić się w zakresie od -1 do 5.",
            status_code=400,
        )
    if attacks < 0:
        temp = SimpleNamespace(
            id=weapon.id,
            name=name,
            range=range,
            attacks=attacks,
            ap=ap,
            tags=tags,
            notes=notes,
        )
        return _render_weapon_form(
            request,
            current_user,
            available_tags,
            temp,
            error="Ataki muszą być liczbą całkowitą większą lub równą 0.",
            status_code=400,
        )

    tags_text, tags_list = _parse_tags(tags)
    allowed_normalized = {_normalize_token(tag) for tag in available_tags}
    invalid = [tag for tag in tags_list if _normalize_token(tag) not in allowed_normalized]
    if invalid:
        temp = SimpleNamespace(
            id=weapon.id,
            name=name,
            range=range,
            attacks=attacks,
            ap=ap,
            tags=tags_text,
            notes=notes,
        )
        error = "Nieznane tagi: " + ", ".join(invalid)
        return _render_weapon_form(request, current_user, available_tags, temp, error=error, status_code=400)

    weapon.name = name
    weapon.range = normalized_range
    weapon.attacks = attacks
    weapon.ap = ap
    weapon.tags = tags_text
    weapon.notes = notes
    weapon.cached_cost = costs.weapon_cost(weapon, quality=4)
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
