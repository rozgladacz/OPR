from __future__ import annotations

import math
from typing import Iterable

import json
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..data import abilities as ability_catalog
from ..db import get_db
from ..security import get_current_user
from ..services import costs, utils

router = APIRouter(prefix="/armories", tags=["armories"])
templates = Jinja2Templates(directory="app/templates")

OVERRIDABLE_FIELDS = ("name", "range", "attacks", "ap", "tags", "notes")

WEAPON_DEFINITIONS = ability_catalog.definitions_by_type("weapon")
WEAPON_DEFINITION_MAP = {definition.slug: definition for definition in WEAPON_DEFINITIONS}
WEAPON_DEFINITION_PAYLOAD = [ability_catalog.to_dict(definition) for definition in WEAPON_DEFINITIONS]
WEAPON_SYNONYMS = {
    "deadly": "zabojczy",
    "blast": "rozprysk",
    "indirect": "niebezposredni",
    "impact": "impet",
    "lock on": "namierzanie",
    "limited": "zuzywalny",
    "reliable": "niezawodny",
    "rending": "rozrywajacy",
    "precise": "precyzyjny",
    "corrosive": "zracy",
    "assault": "szturmowa",
    "no cover": "bez_oslon",
    "brutal": "brutalny",
    "brutalny": "brutalny",
    "brutalna": "brutalny",
    "bez regeneracji": "brutalny",
    "bez regegenracji": "brutalny",
    "no regen": "brutalny",
    "no regeneration": "brutalny",
    "overcharge": "podkrecenie",
    "overclock": "podkrecenie",
}

RANGE_OPTIONS = []
for value in sorted(costs.RANGE_TABLE.keys()):
    label = "Wręcz" if value == 0 else f"{value}\""
    RANGE_OPTIONS.append({"value": str(value), "label": label})



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


def _trait_base_and_value(trait: str) -> tuple[str, str]:
    normalized = costs.normalize_name(trait)
    number = costs.extract_number(normalized)
    value = ""
    base = normalized.strip()
    if number:
        if abs(number - int(number)) < 1e-6:
            number_text = str(int(number))
        else:
            number_text = str(number)
        if "(" in normalized and normalized.endswith(")"):
            base = normalized.split("(", 1)[0].strip()
        else:
            base = normalized.split(number_text, 1)[0].strip()
        value = number_text
    return base, value


def _weapon_tags_payload(tags_text: str | None) -> list[dict]:
    payload: list[dict] = []
    if not tags_text:
        return payload
    traits = costs.split_traits(tags_text)
    for trait in traits:
        base, value = _trait_base_and_value(trait)
        slug = WEAPON_SYNONYMS.get(base, base.replace(" ", "_"))
        definition = WEAPON_DEFINITION_MAP.get(slug)
        value_text = value
        if definition and not definition.value_label:
            value_text = ""
        label = (
            ability_catalog.display_with_value(definition, value_text)
            if definition
            else trait.strip()
        )
        description = ""
        if definition:
            description = ability_catalog.description_with_value(
                definition, value_text
            )
        if not description:
            description = trait.strip()
        payload.append(
            {
                "slug": definition.slug if definition else "__custom__",
                "value": value_text,
                "label": label,
                "raw": trait.strip(),
                "description": description,
            }
        )
    return payload


def _serialize_weapon_tags(items: list[dict]) -> str:
    entries: list[str] = []
    for item in items or []:
        slug = item.get("slug")
        raw = (item.get("raw") or "").strip()
        value = item.get("value")
        definition = WEAPON_DEFINITION_MAP.get(slug or "") if slug != "__custom__" else None
        if definition:
            value_text = str(value).strip() if value is not None else ""
            if definition.value_label and not value_text:
                entries.append(definition.display_name())
            else:
                entries.append(ability_catalog.display_with_value(definition, value_text))
        elif raw:
            entries.append(raw)
    return ", ".join(entries)


def _parse_ability_payload(text: str | None) -> list[dict]:
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "slug": item.get("slug"),
                "value": item.get("value", ""),
                "label": item.get("label", ""),
                "raw": item.get("raw", ""),
            }
        )
    return result

def _armory_weapons(db: Session, armory: models.Armory) -> utils.ArmoryWeaponCollection:
    return utils.load_armory_weapons(db, armory)


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
        cached = weapon.cached_cost
        needs_refresh = cached is None or not math.isfinite(float(cached))
        if needs_refresh and _update_weapon_cost(weapon):
            updated = True
    if updated:
        db.flush()


def _weapon_form_values(weapon: models.Weapon | None) -> dict:
    if not weapon:

        return {
            "name": "",
            "range": "",
            "attacks": "1",
            "ap": "0",
            "tags": "",
            "notes": "",
            "abilities": [],
        }
    return {
        "name": weapon.effective_name,
        "range": weapon.effective_range,
        "attacks": str(weapon.display_attacks),
        "ap": str(weapon.effective_ap),
        "tags": weapon.effective_tags or "",
        "notes": weapon.effective_notes or "",
        "abilities": _weapon_tags_payload(weapon.effective_tags),

    }


def _weapon_tree_payload(weapon_rows: Iterable[dict]) -> list[dict]:
    node_map: dict[int, dict] = {}
    roots: list[dict] = []

    for index, entry in enumerate(weapon_rows):
        weapon = entry.get("instance")
        if not weapon or weapon.id is None:
            continue
        ability_payload = list(entry.get("abilities") or [])
        overrides = dict(entry.get("overrides") or {})
        cost_value = entry.get("cost")
        cost_float = float(cost_value) if cost_value is not None else 0.0
        range_text = weapon.effective_range or ""
        ability_labels = [
            ability.get("label")
            or ability.get("raw")
            or ability.get("slug")
            or ""
            for ability in ability_payload
        ]
        ability_descriptions = [
            ability.get("description") or ability.get("raw") or ""
            for ability in ability_payload
        ]
        parent_name = weapon.parent.effective_name if weapon.parent else None
        node_map[weapon.id] = {
            "id": weapon.id,
            "parent_id": weapon.parent_id,
            "name": weapon.effective_name,
            "name_sort": (weapon.effective_name or "").casefold(),
            "range": range_text,
            "range_value": costs.normalize_range_value(range_text),
            "attacks": weapon.display_attacks,
            "attacks_value": float(weapon.effective_attacks),
            "ap": weapon.effective_ap,
            "abilities": ability_payload,
            "abilities_sort": " ".join(ability_labels).casefold(),
            "cost": cost_float,
            "cost_display": f"{cost_float:.2f}",
            "overrides": overrides,
            "has_parent": weapon.parent_id is not None,
            "parent_name": parent_name,
            "children": [],
            "level": 0,
            "default_order": index,
            "search_source": " ".join(
                part
                for part in (
                    weapon.effective_name,
                    range_text,
                    str(weapon.display_attacks),
                    str(weapon.effective_ap),
                    parent_name,
                    " ".join(ability_labels),
                    " ".join(ability_descriptions),
                )
                if part
            ),
            "edit_url": f"/armories/{weapon.armory_id}/weapons/{weapon.id}/edit",
            "delete_url": f"/armories/{weapon.armory_id}/weapons/{weapon.id}/delete",
        }

    for entry in weapon_rows:
        weapon = entry.get("instance")
        if not weapon or weapon.id is None:
            continue
        node = node_map.get(weapon.id)
        if not node:
            continue
        parent_id = weapon.parent_id
        if parent_id and parent_id in node_map:
            node_map[parent_id]["children"].append(node)
        else:
            roots.append(node)

    def _finalize(nodes: list[dict], level: int = 0) -> None:
        nodes.sort(key=lambda item: item.get("name_sort", ""))
        for position, node in enumerate(nodes):
            node["level"] = level
            node["default_order"] = position
            _finalize(node.get("children", []), level + 1)

    _finalize(roots, 0)
    return roots


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


def _sync_descendant_variants(db: Session, armory: models.Armory) -> None:
    stack: list[models.Armory] = list(armory.variants)
    while stack:
        variant = stack.pop()
        utils.ensure_armory_variant_sync(db, variant)
        stack.extend(variant.variants)


@router.get("", response_class=HTMLResponse)
def list_armories(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = (
        select(models.Armory)
        .options(
            selectinload(models.Armory.parent),
            selectinload(models.Armory.owner),
        )
        .order_by(models.Armory.name)
    )
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


@router.post("/{armory_id}/takeover")
def takeover_armory(
    armory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Brak uprawnień do przejęcia zbrojowni",
        )
    armory.owner_id = None
    db.commit()
    return RedirectResponse(url="/armories", status_code=303)


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

    weapon_collection = _armory_weapons(db, armory)
    weapons = list(weapon_collection.items)
    weapon_tree = weapon_collection.payload
    _refresh_costs(db, weapons)

    parent_chain = _parent_chain(armory)
    can_edit = current_user.is_admin or armory.owner_id == current_user.id
    can_delete = can_edit and not armory.variants and not armory.armies

    weapon_rows = []
    for weapon in weapons:
        overrides = {field: getattr(weapon, field) is not None for field in OVERRIDABLE_FIELDS}
        cached_cost = weapon.effective_cached_cost
        if cached_cost is None:
            cached_cost = costs.weapon_cost(weapon)
        weapon_rows.append(
            {
                "instance": weapon,
                "overrides": overrides,
                "cost": cached_cost,
                "abilities": _weapon_tags_payload(weapon.effective_tags),
            }
        )

    weapon_tree = _weapon_tree_payload(weapon_rows)

    db.commit()

    return templates.TemplateResponse(
        "armory_detail.html",
        {
            "request": request,
            "user": current_user,
            "armory": armory,
            "weapons": weapon_rows,
            "weapon_tree": weapon_tree,
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
        weapon_collection = _armory_weapons(db, armory)
        weapons = list(weapon_collection.items)
        weapon_tree = weapon_collection.payload
        weapon_rows = [
            {
                "instance": weapon,
                "overrides": {
                    field: getattr(weapon, field) is not None
                    for field in OVERRIDABLE_FIELDS
                },
                "cost": costs.weapon_cost(weapon),
                "abilities": _weapon_tags_payload(weapon.effective_tags),
            }
            for weapon in weapons
        ]
        weapon_tree = _weapon_tree_payload(weapon_rows)
        return templates.TemplateResponse(
            "armory_detail.html",
            {
                "request": request,
                "user": current_user,
                "armory": armory,
                "weapons": weapon_rows,
                "weapon_tree": weapon_tree,
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

    weapon_collection = _armory_weapons(db, source)
    for weapon in weapon_collection.items:
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
        cached_cost = weapon.effective_cached_cost
        if cached_cost is not None:
            clone.cached_cost = cached_cost
        else:
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
            "range_options": RANGE_OPTIONS,
            "parent_defaults": None,
            "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,

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

    abilities: str | None = Form(None),

    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)

    cleaned_name = name.strip()

    ability_items = _parse_ability_payload(abilities)

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

                    "tags": _serialize_weapon_tags(ability_items),
                    "notes": notes or "",
                    "abilities": ability_items,
                },
                "range_options": RANGE_OPTIONS,
                "parent_defaults": None,
                "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,
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
                    "tags": _serialize_weapon_tags(ability_items),
                    "notes": notes or "",
                    "abilities": ability_items,
                },
                "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,
                "error": str(exc),
            },
        )

    if attacks_value is None:
        attacks_value = 1.0
    if ap_value is None:
        ap_value = 0


    tags_text = _serialize_weapon_tags(ability_items)

    weapon = models.Weapon(
        armory=armory,
        owner_id=armory.owner_id,
        name=cleaned_name,
        range=range.strip(),
        attacks=attacks_value,
        ap=ap_value,

        tags=tags_text or None,

        notes=(notes or "").strip() or None,
    )
    weapon.cached_cost = costs.weapon_cost(weapon)
    db.add(weapon)
    db.flush()
    _sync_descendant_variants(db, armory)
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
            "range_options": RANGE_OPTIONS,
            "parent_defaults": _weapon_form_values(weapon.parent) if weapon and weapon.parent else None,

            "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,

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

    abilities: str | None = Form(None),

    notes: str | None = Form(None),
    action: str = Form("save"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)
    weapon = _get_weapon(db, armory, weapon_id)

    cleaned_name = name.strip()

    ability_items = _parse_ability_payload(abilities)

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

                    "tags": _serialize_weapon_tags(ability_items),
                    "notes": notes or "",
                    "abilities": ability_items,
                },
                "range_options": RANGE_OPTIONS,
                "parent_defaults": _weapon_form_values(weapon.parent) if weapon and weapon.parent else None,
                "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,

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
                    "tags": _serialize_weapon_tags(ability_items),
                    "notes": notes or "",
                    "abilities": ability_items,
                },
                "range_options": RANGE_OPTIONS,
                "parent_defaults": _weapon_form_values(weapon.parent) if weapon and weapon.parent else None,
                "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,

                "error": str(exc),
            },
        )

    cleaned_range = range.strip()
    tags_text = _serialize_weapon_tags(ability_items)
    cleaned_notes_text = (notes or "").strip()

    if action == "create_weapon":
        new_weapon = models.Weapon(
            armory=armory,
            owner_id=armory.owner_id,
            name=cleaned_name,
            range=cleaned_range,
            attacks=attacks_value if attacks_value is not None else 1.0,
            ap=ap_value if ap_value is not None else 0,
            tags=tags_text or None,
            notes=cleaned_notes_text or None,
        )
        _update_weapon_cost(new_weapon)
        db.add(new_weapon)
        db.flush()
        _sync_descendant_variants(db, armory)
        db.commit()
        return RedirectResponse(
            url=f"/armories/{armory.id}/weapons/{new_weapon.id}/edit", status_code=303
        )

    if action == "create_variant":
        parent = weapon
        new_weapon = models.Weapon(
            armory=armory,
            owner_id=armory.owner_id,
            parent=parent,
        )

        if cleaned_name != parent.effective_name:
            new_weapon.name = cleaned_name

        if cleaned_range != parent.effective_range:
            new_weapon.range = cleaned_range

        if attacks_value is not None and not math.isclose(
            attacks_value, parent.effective_attacks, rel_tol=1e-9, abs_tol=1e-9
        ):
            new_weapon.attacks = attacks_value

        if ap_value is not None and ap_value != parent.effective_ap:
            new_weapon.ap = ap_value

        cleaned_tags_value = tags_text or None
        if cleaned_tags_value != parent.effective_tags:
            new_weapon.tags = cleaned_tags_value

        cleaned_notes_value = cleaned_notes_text or None
        if cleaned_notes_value != parent.effective_notes:
            new_weapon.notes = cleaned_notes_value

        _update_weapon_cost(new_weapon)
        db.add(new_weapon)
        db.flush()
        _sync_descendant_variants(db, armory)
        db.commit()
        return RedirectResponse(
            url=f"/armories/{armory.id}/weapons/{new_weapon.id}/edit", status_code=303
        )

    if weapon.parent:
        parent = weapon.parent
        weapon.name = None if cleaned_name == parent.effective_name else cleaned_name
    else:
        weapon.name = cleaned_name

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

    cleaned_tags = tags_text or None
    if weapon.parent:
        weapon.tags = None if cleaned_tags == weapon.parent.effective_tags else cleaned_tags
    else:
        weapon.tags = cleaned_tags

    cleaned_notes = cleaned_notes_text or None
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
