from __future__ import annotations

import math
from typing import Iterable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs, utils

router = APIRouter(prefix="/armories", tags=["armories"])
templates = Jinja2Templates(directory="app/templates")

OVERRIDABLE_FIELDS = ("name", "range", "attacks", "ap", "tags", "notes")


def _ensure_armory_view_access(armory: models.Armory, user: models.User) -> None:
    if user.is_admin:
        return
    if armory.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do zbrojowni")


def _ensure_armory_edit_access(armory: models.Armory, user: models.User) -> None:
    if user.is_admin:
        return
    if armory.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Brak uprawnień do edycji zbrojowni")


def _get_armory(db: Session, armory_id: int) -> models.Armory:
    armory = db.get(models.Armory, armory_id)
    if not armory:
        raise HTTPException(status_code=404)
    return armory


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "on", "yes"}


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError as exc:  # pragma: no cover - validation branch
        raise ValueError("Nieprawidłowa wartość liczby ataków") from exc


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:  # pragma: no cover - validation branch
        raise ValueError("Nieprawidłowa wartość AP") from exc


def _armory_weapons(db: Session, armory: models.Armory) -> list[models.Weapon]:
    weapons = (
        db.execute(
            select(models.Weapon).where(models.Weapon.armory_id == armory.id)
        ).scalars().all()
    )
    weapons.sort(key=lambda weapon: weapon.effective_name.casefold())
    return weapons


def _update_weapon_cost(weapon: models.Weapon) -> bool:
    if weapon.parent and not weapon.has_overrides():
        if weapon.cached_cost is not None:
            weapon.cached_cost = None
            return True
        return False
    recalculated = costs.weapon_cost(weapon)
    if weapon.cached_cost is None or not math.isclose(
        weapon.cached_cost, recalculated, rel_tol=1e-9, abs_tol=1e-9
    ):
        weapon.cached_cost = recalculated
        return True
    return False


def _refresh_costs(db: Session, weapons: Iterable[models.Weapon]) -> None:
    updated = False
    for weapon in weapons:
        if _update_weapon_cost(weapon):
            updated = True
    if updated:
        db.flush()


def _weapon_form_values(weapon: models.Weapon | None) -> dict:
    if not weapon:
        return {"name": "", "range": "", "attacks": "1", "ap": "0", "tags": "", "notes": ""}
    return {
        "name": weapon.effective_name,
        "range": weapon.effective_range,
        "attacks": str(weapon.effective_attacks),
        "ap": str(weapon.effective_ap),
        "tags": weapon.effective_tags or "",
        "notes": weapon.effective_notes or "",
    }


def _delete_weapon_chain(db: Session, weapon: models.Weapon) -> None:
    children = db.execute(
        select(models.Weapon).where(models.Weapon.parent_id == weapon.id)
    ).scalars().all()
    for child in children:
        _delete_weapon_chain(db, child)
    db.delete(weapon)


def _parent_chain(armory: models.Armory) -> list[models.Armory]:
    chain: list[models.Armory] = []
    current = armory.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    return chain


@router.get("", response_class=HTMLResponse)
def list_armories(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = select(models.Armory).order_by(models.Armory.name)
    if not current_user.is_admin:
        query = query.where(
            or_(
                models.Armory.owner_id == current_user.id,
                models.Armory.owner_id.is_(None),
            )
        )
    armories = db.execute(query).scalars().all()
    mine, global_items, others = utils.split_owned(armories, current_user)
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


@router.get("/new", response_class=HTMLResponse)
def new_armory_form(
    request: Request,
    current_user: models.User = Depends(get_current_user()),
):
    return templates.TemplateResponse(
        "armory_new.html",
        {"request": request, "user": current_user, "error": None},
    )


@router.post("/new")
def create_armory(
    request: Request,
    name: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    cleaned_name = name.strip()
    if not cleaned_name:
        return templates.TemplateResponse(
            "armory_new.html",
            {
                "request": request,
                "user": current_user,
                "error": "Nazwa zbrojowni jest wymagana.",
            },
        )

    owner_id = current_user.id
    if _parse_bool(is_global):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Tylko administrator może tworzyć globalne zbrojownie")
        owner_id = None

    armory = models.Armory(name=cleaned_name, owner_id=owner_id)
    db.add(armory)
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)


@router.get("/{armory_id}", response_class=HTMLResponse)
def view_armory(
    armory_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    armory = _get_armory(db, armory_id)
    _ensure_armory_view_access(armory, current_user)

    if armory.parent_id is not None:
        utils.ensure_armory_variant_sync(db, armory)

    weapons = _armory_weapons(db, armory)
    _refresh_costs(db, weapons)

    parent_chain = _parent_chain(armory)
    can_edit = current_user.is_admin or armory.owner_id == current_user.id
    can_delete = can_edit and not armory.variants and not armory.armies

    weapon_rows = []
    for weapon in weapons:
        overrides = {field: getattr(weapon, field) is not None for field in OVERRIDABLE_FIELDS}
        weapon_rows.append(
            {
                "instance": weapon,
                "overrides": overrides,
                "cost": costs.weapon_cost(weapon),
            }
        )

    db.commit()

    return templates.TemplateResponse(
        "armory_detail.html",
        {
            "request": request,
            "user": current_user,
            "armory": armory,
            "weapons": weapon_rows,
            "can_edit": can_edit,
            "can_delete": can_delete,
            "parent_chain": list(reversed(parent_chain)),
            "form_values": _weapon_form_values(None),
            "error": None,
        },
    )


@router.post("/{armory_id}/rename")
def rename_armory(
    armory_id: int,
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        weapons = _armory_weapons(db, armory)
        weapon_rows = [
            {"instance": weapon, "overrides": {field: getattr(weapon, field) is not None for field in OVERRIDABLE_FIELDS}, "cost": costs.weapon_cost(weapon)}
            for weapon in weapons
        ]
        return templates.TemplateResponse(
            "armory_detail.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapons": weapon_rows,
                "can_edit": True,
                "can_delete": not armory.variants and not armory.armies,
                "parent_chain": list(reversed(_parent_chain(armory))),
                "form_values": _weapon_form_values(None),
                "error": "Nazwa zbrojowni jest wymagana.",
            },
        )

    armory.name = cleaned_name
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)


@router.post("/{armory_id}/delete")
def delete_armory(
    armory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)

    has_variants = db.execute(
        select(models.Armory.id).where(models.Armory.parent_id == armory.id)
    ).first()
    if has_variants:
        raise HTTPException(status_code=400, detail="Najpierw usuń powiązane warianty")
    has_armies = db.execute(
        select(models.Army.id).where(models.Army.armory_id == armory.id)
    ).first()
    if has_armies:
        raise HTTPException(status_code=400, detail="Zbrojownia jest używana przez armię")

    db.delete(armory)
    db.commit()
    return RedirectResponse(url="/armories", status_code=303)


@router.post("/{armory_id}/copy")
def copy_armory(
    armory_id: int,
    request: Request,
    name: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    source = _get_armory(db, armory_id)
    _ensure_armory_view_access(source, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nazwa kopii jest wymagana")

    owner_id = current_user.id
    if _parse_bool(is_global):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Tylko administrator może tworzyć globalne zbrojownie")
        owner_id = None

    new_armory = models.Armory(name=cleaned_name, owner_id=owner_id)
    db.add(new_armory)
    db.flush()

    weapons = _armory_weapons(db, source)
    for weapon in weapons:
        clone = models.Weapon(
            armory=new_armory,
            owner_id=new_armory.owner_id,
            name=weapon.effective_name,
            range=weapon.effective_range,
            attacks=weapon.effective_attacks,
            ap=weapon.effective_ap,
            tags=weapon.effective_tags,
            notes=weapon.effective_notes,
        )
        clone.cached_cost = costs.weapon_cost(clone)
        db.add(clone)

    db.commit()
    return RedirectResponse(url=f"/armories/{new_armory.id}", status_code=303)


@router.post("/{armory_id}/variant")
def create_variant(
    armory_id: int,
    request: Request,
    name: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    base_armory = _get_armory(db, armory_id)
    _ensure_armory_view_access(base_armory, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nazwa wariantu jest wymagana")

    owner_id = current_user.id
    if _parse_bool(is_global):
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Tylko administrator może tworzyć globalne zbrojownie")
        owner_id = None

    variant = models.Armory(name=cleaned_name, owner_id=owner_id, parent=base_armory)
    db.add(variant)
    db.flush()
    utils.ensure_armory_variant_sync(db, variant)
    db.commit()
    return RedirectResponse(url=f"/armories/{variant.id}", status_code=303)


@router.get("/{armory_id}/weapons/new", response_class=HTMLResponse)
def new_weapon_form(
    armory_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)

    return templates.TemplateResponse(
        "armory_weapon_form.html",
        {
            "request": request,
            "user": current_user,
            "armory": armory,
            "weapon": None,
            "form_values": _weapon_form_values(None),
            "error": None,
        },
    )


@router.post("/{armory_id}/weapons/new")
def create_weapon(
    armory_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(""),
    attacks: str = Form("1"),
    ap: str = Form("0"),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapon": None,
                "form_values": {
                    "name": name,
                    "range": range,
                    "attacks": attacks,
                    "ap": ap,
                    "tags": tags or "",
                    "notes": notes or "",
                },
                "error": "Nazwa broni jest wymagana.",
            },
        )

    try:
        attacks_value = _parse_optional_float(attacks)
        ap_value = _parse_optional_int(ap)
    except ValueError as exc:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapon": None,
                "form_values": {
                    "name": name,
                    "range": range,
                    "attacks": attacks,
                    "ap": ap,
                    "tags": tags or "",
                    "notes": notes or "",
                },
                "error": str(exc),
            },
        )

    if attacks_value is None:
        attacks_value = 1.0
    if ap_value is None:
        ap_value = 0

    weapon = models.Weapon(
        armory=armory,
        owner_id=armory.owner_id,
        name=cleaned_name,
        range=range.strip(),
        attacks=attacks_value,
        ap=ap_value,
        tags=(tags or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    weapon.cached_cost = costs.weapon_cost(weapon)
    db.add(weapon)
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)


def _get_weapon(db: Session, armory: models.Armory, weapon_id: int) -> models.Weapon:
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon or weapon.armory_id != armory.id:
        raise HTTPException(status_code=404)
    return weapon


@router.get("/{armory_id}/weapons/{weapon_id}/edit", response_class=HTMLResponse)
def edit_weapon_form(
    armory_id: int,
    weapon_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)
    weapon = _get_weapon(db, armory, weapon_id)

    return templates.TemplateResponse(
        "armory_weapon_form.html",
        {
            "request": request,
            "user": current_user,
            "armory": armory,
            "weapon": weapon,
            "form_values": _weapon_form_values(weapon),
            "error": None,
        },
    )


@router.post("/{armory_id}/weapons/{weapon_id}/edit")
def update_weapon(
    armory_id: int,
    weapon_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(""),
    attacks: str = Form("1"),
    ap: str = Form("0"),
    tags: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)
    weapon = _get_weapon(db, armory, weapon_id)

    cleaned_name = name.strip()
    if not cleaned_name:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapon": weapon,
                "form_values": {
                    "name": name,
                    "range": range,
                    "attacks": attacks,
                    "ap": ap,
                    "tags": tags or "",
                    "notes": notes or "",
                },
                "error": "Nazwa broni jest wymagana.",
            },
        )

    try:
        attacks_value = _parse_optional_float(attacks)
        ap_value = _parse_optional_int(ap)
    except ValueError as exc:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapon": weapon,
                "form_values": {
                    "name": name,
                    "range": range,
                    "attacks": attacks,
                    "ap": ap,
                    "tags": tags or "",
                    "notes": notes or "",
                },
                "error": str(exc),
            },
        )

    if weapon.parent:
        parent = weapon.parent
        weapon.name = None if cleaned_name == parent.effective_name else cleaned_name
    else:
        weapon.name = cleaned_name

    cleaned_range = range.strip()
    if weapon.parent:
        weapon.range = None if cleaned_range == weapon.parent.effective_range else cleaned_range
    else:
        weapon.range = cleaned_range

    if attacks_value is None:
        if weapon.parent:
            weapon.attacks = None
        else:
            attacks_value = weapon.attacks if weapon.attacks is not None else 1.0
            weapon.attacks = attacks_value
    else:
        if weapon.parent and math.isclose(attacks_value, weapon.parent.effective_attacks, rel_tol=1e-9, abs_tol=1e-9):
            weapon.attacks = None
        else:
            weapon.attacks = attacks_value

    if ap_value is None:
        if weapon.parent:
            weapon.ap = None
        else:
            weapon.ap = weapon.ap if weapon.ap is not None else 0
    else:
        if weapon.parent and ap_value == weapon.parent.effective_ap:
            weapon.ap = None
        else:
            weapon.ap = ap_value

    cleaned_tags = (tags or "").strip() or None
    if weapon.parent:
        weapon.tags = None if cleaned_tags == weapon.parent.effective_tags else cleaned_tags
    else:
        weapon.tags = cleaned_tags

    cleaned_notes = (notes or "").strip() or None
    if weapon.parent:
        weapon.notes = None if cleaned_notes == weapon.parent.effective_notes else cleaned_notes
    else:
        weapon.notes = cleaned_notes

    _update_weapon_cost(weapon)
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)


@router.post("/{armory_id}/weapons/{weapon_id}/delete")
def delete_weapon(
    armory_id: int,
    weapon_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)
    weapon = _get_weapon(db, armory, weapon_id)
    _delete_weapon_chain(db, weapon)
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)
