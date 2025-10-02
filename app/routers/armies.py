from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..data import abilities as ability_catalog
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs, utils

router = APIRouter(prefix="/armies", tags=["armies"])
templates = Jinja2Templates(directory="app/templates")


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


PASSIVE_DEFINITIONS = [
    entry
    for entry in (
        ability_catalog.to_dict(definition)
        for definition in ability_catalog.definitions_by_type("passive")
    )
    if not _is_hidden_trait(entry.get("slug"))
]


def _ensure_army_view_access(army: models.Army, user: models.User) -> None:
    if user.is_admin:
        return
    if army.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do armii")


def _ensure_army_edit_access(army: models.Army, user: models.User) -> None:
    if user.is_admin:
        return
    if army.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Brak dostępu do armii")


def _get_default_ruleset(db: Session) -> models.RuleSet | None:
    return (
        db.execute(select(models.RuleSet).order_by(models.RuleSet.id))
        .scalars()
        .first()
    )


def _available_armories(db: Session, user: models.User) -> list[models.Armory]:
    query = select(models.Armory).order_by(models.Armory.name)
    if not user.is_admin:
        query = query.where(
            or_(
                models.Armory.owner_id == user.id,
                models.Armory.owner_id.is_(None),
            )
        )
    return db.execute(query).scalars().all()


def _ensure_armory_access(armory: models.Armory, user: models.User) -> None:
    if user.is_admin:
        return
    if armory.owner_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Brak dostępu do zbrojowni")


def _armory_weapons(db: Session, armory: models.Armory) -> list[models.Weapon]:
    utils.ensure_armory_variant_sync(db, armory)
    weapons = (
        db.execute(
            select(models.Weapon).where(models.Weapon.armory_id == armory.id)
        ).scalars().all()
    )
    weapons.sort(key=lambda weapon: weapon.effective_name.casefold())
    return weapons


def _ordered_weapons(db: Session, armory: models.Armory, weapon_ids: list[int]) -> list[models.Weapon]:
    if not weapon_ids:
        return []
    utils.ensure_armory_variant_sync(db, armory)
    query = select(models.Weapon).where(
        models.Weapon.armory_id == armory.id,
        models.Weapon.id.in_(weapon_ids),
    )
    weapons = db.execute(query).scalars().all()
    weapon_map = {weapon.id: weapon for weapon in weapons}
    missing_ids = {weapon_id for weapon_id in weapon_ids if weapon_id not in weapon_map}
    if missing_ids:
        raise HTTPException(status_code=404)
    ordered: list[models.Weapon] = []
    seen: set[int] = set()
    for weapon_id in weapon_ids:
        if weapon_id in weapon_map and weapon_id not in seen:
            ordered.append(weapon_map[weapon_id])
            seen.add(weapon_id)
    return ordered


def _passive_payload(unit: models.Unit | None) -> list[dict]:
    flags = unit.flags if unit else None
    payload = utils.passive_flags_to_payload(flags)
    result: list[dict] = []
    for item in payload:
        if not item:
            continue
        if _is_hidden_trait(item.get("slug")):
            continue
        result.append(item)
    return result


def _parse_selection_payload(text: str | None) -> list[dict]:
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _unit_weapon_payload(unit: models.Unit | None) -> list[dict]:
    if not unit:
        return []
    payload: list[dict] = []
    seen: set[int] = set()
    for link in getattr(unit, "weapon_links", []):
        if link.weapon_id is None:
            continue
        name = link.weapon.effective_name if link.weapon else ""
        is_default_flag = bool(getattr(link, "is_default", False))
        count_raw = getattr(link, "default_count", None)
        try:
            count_value = int(count_raw)
        except (TypeError, ValueError):
            count_value = 1 if is_default_flag else 0
        if count_value < 0:
            count_value = 0
        if not is_default_flag and count_value > 0:
            is_default_flag = True
        if not is_default_flag:
            count_value = 0
        payload.append(
            {
                "weapon_id": link.weapon_id,
                "name": name,
                "is_default": is_default_flag,
                "count": count_value,
            }
        )
        seen.add(link.weapon_id)
    if (
        getattr(unit, "default_weapon", None)
        and unit.default_weapon_id
        and unit.default_weapon_id not in seen
    ):
        payload.append(
            {
                "weapon_id": unit.default_weapon_id,
                "name": unit.default_weapon.effective_name,
                "is_default": True,
                "count": 1,
            }
        )
    return payload


def _parse_weapon_payload(
    db: Session, armory: models.Armory, text: str | None
) -> list[tuple[models.Weapon, bool, int]]:
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    results: list[tuple[models.Weapon, bool, int]] = []
    seen: set[int] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        weapon_id = entry.get("weapon_id")
        if weapon_id is None:
            continue
        try:
            weapon_id = int(weapon_id)
        except (TypeError, ValueError):
            continue
        if weapon_id in seen:
            continue
        weapon = db.get(models.Weapon, weapon_id)
        if not weapon or weapon.armory_id != armory.id:
            continue
        count_raw = entry.get("count")
        if count_raw is None:
            count_raw = entry.get("default_count")
        if count_raw is None:
            count_raw = 1 if entry.get("is_default") else 0
        try:
            count_value = int(count_raw)
        except (TypeError, ValueError):
            count_value = 1 if entry.get("is_default") else 0
        if count_value < 0:
            count_value = 0
        is_default_raw = entry.get("is_default")
        is_default = bool(is_default_raw) if is_default_raw is not None else count_value > 0
        if not is_default:
            count_value = 0
        results.append(
            (
                weapon,
                is_default,
                count_value,
            )
        )
        seen.add(weapon_id)
    return results


@router.get("", response_class=HTMLResponse)
def list_armies(
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
    mine, global_items, others = utils.split_owned(armies, current_user)
    return templates.TemplateResponse(
        "armies_list.html",
        {
            "request": request,
            "user": current_user,
            "mine": mine,
            "global_items": global_items,
            "others": others,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_army_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    default_ruleset = _get_default_ruleset(db)
    armories = _available_armories(db, current_user)
    selected_armory_id = armories[0].id if armories else None
    return templates.TemplateResponse(
        "army_form.html",
        {
            "request": request,
            "user": current_user,
            "default_ruleset": default_ruleset,
            "army": None,
            "armories": armories,
            "selected_armory_id": selected_armory_id,
            "error": None,
        },
    )


@router.post("/new")
def create_army(
    request: Request,
    name: str = Form(...),
    armory_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    ruleset = _get_default_ruleset(db)
    if not ruleset:
        raise HTTPException(status_code=404)
    try:
        armory_pk = int(armory_id)
    except ValueError:
        armory = None
    else:
        armory = db.get(models.Armory, armory_pk)

    if not armory:
        armories = _available_armories(db, current_user)
        selected_id = armories[0].id if armories else None
        return templates.TemplateResponse(
            "army_form.html",
            {
                "request": request,
                "user": current_user,
                "default_ruleset": ruleset,
                "army": None,
                "armories": armories,
                "selected_armory_id": selected_id,
                "error": "Wybrana zbrojownia nie istnieje.",
            },
        )

    if not current_user.is_admin and armory.owner_id not in (None, current_user.id):
        armories = _available_armories(db, current_user)
        selected_id = armories[0].id if armories else None
        return templates.TemplateResponse(
            "army_form.html",
            {
                "request": request,
                "user": current_user,
                "default_ruleset": ruleset,
                "army": None,
                "armories": armories,
                "selected_armory_id": selected_id,
                "error": "Brak uprawnień do wybranej zbrojowni.",
            },
        )

    army = models.Army(
        name=name,
        ruleset=ruleset,
        owner_id=current_user.id,
        armory=armory,
    )
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
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_view_access(army, current_user)

    can_edit = current_user.is_admin or army.owner_id == current_user.id
    can_delete = False
    if can_edit:
        has_rosters = db.execute(
            select(models.Roster.id).where(models.Roster.army_id == army.id)
        ).first()
        can_delete = not bool(has_rosters)
    weapons = _armory_weapons(db, army.armory)

    weapon_choices = [
        {"id": weapon.id, "name": weapon.effective_name}
        for weapon in weapons
    ]
    available_armories = _available_armories(db, current_user) if can_edit else []
    active_definitions = ability_registry.definition_payload(db, "active")
    aura_definitions = ability_registry.definition_payload(db, "aura")

    units = []
    for unit in army.units:
        passive_items = [item for item in _passive_payload(unit) if item]
        active_items = ability_registry.unit_ability_payload(unit, "active")
        aura_items = ability_registry.unit_ability_payload(unit, "aura")
        loadout = unit.default_weapon_loadout
        weapon_summary = ", ".join(
            f"{weapon.effective_name} x{count}" if count > 1 else weapon.effective_name
            for weapon, count in loadout
        )
        if not weapon_summary:
            weapon_summary = "-"
        units.append(
            {
                "instance": unit,
                "cost": costs.unit_total_cost(unit),
                "passive_items": passive_items,
                "active_items": active_items,
                "aura_items": aura_items,
                "weapon_summary": weapon_summary,

            }
        )
    return templates.TemplateResponse(
        "army_edit.html",
        {
            "request": request,
            "user": current_user,
            "army": army,
            "units": units,
            "weapons": weapons,

            "weapon_choices": weapon_choices,

            "armories": available_armories,
            "selected_armory_id": army.armory_id,
            "error": None,
            "can_edit": can_edit,
            "can_delete": can_delete,
            "passive_definitions": PASSIVE_DEFINITIONS,
            "active_definitions": active_definitions,
            "aura_definitions": aura_definitions,
        },
    )


@router.post("/{army_id}/update")
def update_army(
    army_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    army.name = name
    db.commit()
    return RedirectResponse(url=f"/armies/{army.id}", status_code=303)


@router.post("/{army_id}/delete")
def delete_army(
    army_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    has_rosters = db.execute(
        select(models.Roster.id).where(models.Roster.army_id == army.id)
    ).first()
    if has_rosters:
        raise HTTPException(status_code=400, detail="Armia jest używana przez rozpiskę")

    db.delete(army)
    db.commit()
    return RedirectResponse(url="/armies", status_code=303)


@router.post("/{army_id}/units/new")
def add_unit(
    army_id: int,
    name: str = Form(...),
    quality: int = Form(...),
    defense: int = Form(...),
    toughness: int = Form(...),
    weapons: str | None = Form(None),
    passive_abilities: str | None = Form(None),
    active_abilities: str | None = Form(None),
    aura_abilities: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)


    weapon_entries = _parse_weapon_payload(db, army.armory, weapons)
    passive_items = _parse_selection_payload(passive_abilities)
    active_items = _parse_selection_payload(active_abilities)
    aura_items = _parse_selection_payload(aura_abilities)
    active_links = ability_registry.build_unit_abilities(db, active_items, "active")
    aura_links = ability_registry.build_unit_abilities(db, aura_items, "aura")

    unit = models.Unit(
        name=name,
        quality=quality,
        defense=defense,
        toughness=toughness,
        flags=utils.passive_payload_to_flags(passive_items),
        army=army,
        owner_id=army.owner_id if army.owner_id is not None else current_user.id,
    )
    weapon_links: list[models.UnitWeapon] = []
    default_assigned = False
    fallback_weapon = None
    for weapon, is_default, count in weapon_entries:
        link = models.UnitWeapon(
            weapon=weapon,
            is_default=is_default,
            default_count=count,
        )
        weapon_links.append(link)
        if fallback_weapon is None and count > 0:
            fallback_weapon = weapon
        if is_default and count > 0 and not default_assigned:
            unit.default_weapon = weapon
            default_assigned = True
    if not default_assigned:
        unit.default_weapon = fallback_weapon
    unit.weapon_links = weapon_links
    unit.abilities = active_links + aura_links
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
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    weapons = _armory_weapons(db, army.armory)

    weapon_choices = [
        {"id": weapon.id, "name": weapon.effective_name}
        for weapon in weapons
    ]
    active_definitions = ability_registry.definition_payload(db, "active")
    aura_definitions = ability_registry.definition_payload(db, "aura")

    return templates.TemplateResponse(
        "unit_form.html",
        {
            "request": request,
            "user": current_user,
            "army": army,
            "unit": unit,
            "weapons": weapons,
            "weapon_choices": weapon_choices,
            "weapon_payload": _unit_weapon_payload(unit),
            "passive_definitions": PASSIVE_DEFINITIONS,
            "passive_selected": _passive_payload(unit),
            "active_definitions": active_definitions,
            "active_selected": ability_registry.unit_ability_payload(unit, "active"),
            "aura_definitions": aura_definitions,
            "aura_selected": ability_registry.unit_ability_payload(unit, "aura"),
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
    weapons: str | None = Form(None),
    passive_abilities: str | None = Form(None),
    active_abilities: str | None = Form(None),
    aura_abilities: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    unit.name = name
    unit.quality = quality
    unit.defense = defense
    unit.toughness = toughness

    passive_items = _parse_selection_payload(passive_abilities)
    unit.flags = utils.passive_payload_to_flags(passive_items)
    weapon_entries = _parse_weapon_payload(db, army.armory, weapons)
    weapon_links: list[models.UnitWeapon] = []
    default_assigned = False
    fallback_weapon = None
    for weapon, is_default, count in weapon_entries:
        link = models.UnitWeapon(
            weapon=weapon,
            is_default=is_default,
            default_count=count,
        )
        weapon_links.append(link)
        if fallback_weapon is None and count > 0:
            fallback_weapon = weapon
        if is_default and count > 0 and not default_assigned:
            unit.default_weapon = weapon
            default_assigned = True
    if not default_assigned:
        unit.default_weapon = fallback_weapon
    unit.weapon_links = weapon_links
    active_items = _parse_selection_payload(active_abilities)
    aura_items = _parse_selection_payload(aura_abilities)
    unit.abilities = ability_registry.build_unit_abilities(db, active_items, "active") + ability_registry.build_unit_abilities(db, aura_items, "aura")

    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)


@router.post("/{army_id}/units/{unit_id}/delete")
def delete_unit(
    army_id: int,
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    db.delete(unit)
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)
