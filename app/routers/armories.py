from __future__ import annotations

import logging
import math
from typing import Iterable

import json
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..data import abilities as ability_catalog
from ..db import get_db
from ..paths import TEMPLATES_DIR
from ..security import get_current_user
from ..services import costs, utils

router = APIRouter(prefix="/armories", tags=["armories"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = logging.getLogger(__name__)

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
    "penetrating": "przebijajaca",
    "corrosive": "zracy",
    "assault": "szturmowa",
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
    recalculated = costs.weapon_cost(weapon, use_cached=False)
    if weapon.cached_cost is None or not math.isclose(
        weapon.cached_cost, recalculated, rel_tol=1e-9, abs_tol=1e-9
    ):
        weapon.cached_cost = recalculated
        return True
    return False


def _resolve_local_parent_for_variant(
    db: Session,
    armory: models.Armory,
    weapon: models.Weapon,
) -> models.Weapon:
    if weapon.armory_id == armory.id:
        return weapon

    visited: set[int] = set()
    current: models.Weapon | None = weapon
    while current is not None:
        current_id = getattr(current, "id", None)
        if current_id is None or current_id in visited:
            break
        visited.add(current_id)

        local_candidate = (
            db.execute(
                select(models.Weapon)
                .where(
                    models.Weapon.armory_id == armory.id,
                    models.Weapon.parent_id == current_id,
                )
                .order_by(models.Weapon.id.asc())
            )
            .scalars()
            .first()
        )
        if local_candidate is not None:
            return local_candidate

        current = current.parent

    return weapon


def _refresh_costs(db: Session, weapons: Iterable[models.Weapon]) -> None:
    updated = False
    for weapon in weapons:
        if _update_weapon_cost(weapon):
            updated = True
    if updated:
        db.flush()

def _render_armory_detail(
    *,
    request: Request,
    db: Session,
    armory: models.Armory,
    current_user: models.User,
    error: str | None = None,
    warning: str | None = None,
    selected_weapon_id: int | None = None,
) -> HTMLResponse:
    weapon_collection = _armory_weapons(db, armory)
    weapons = list(weapon_collection.items)
    weapon_tree = weapon_collection.payload
    _refresh_costs(db, weapons)

    if selected_weapon_id is not None and not any(w.id == selected_weapon_id for w in weapons):
        warning = (
            f"Broń o ID {selected_weapon_id} nie jest dostępna w aktualnym widoku. "
            "Odśwież stronę lub ponownie wejdź w edycję tej broni, "
            "aby zweryfikować, czy to problem danych czy tylko widoku."
        )
        selected_weapon_id = None

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
            "error": error,
            "warning": warning,
            "selected_weapon_id": selected_weapon_id,
        },
    )


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


def _weapon_inheritance_panel_context(
    db: Session,
    armory: models.Armory,
    weapon: models.Weapon | None = None,
) -> dict:
    lineage: list[models.Armory] = []
    current: models.Armory | None = armory
    visited: set[int] = set()
    while current and current.id not in visited:
        lineage.append(current)
        visited.add(current.id)
        current = current.parent

    source_armories = [
        {
            "id": item.id,
            "name": item.name,
            "depth": index,
            "is_current": index == 0,
        }
        for index, item in enumerate(lineage)
    ]

    parent_weapon_options: list[dict] = []
    source_weapon_trees: dict[str, list[dict]] = {}
    if source_armories:
        for source in source_armories:
            source_armory = db.get(models.Armory, source["id"])
            if source_armory is None:
                continue
            source_collection = _armory_weapons(db, source_armory)
            source_weapon_trees[str(source["id"])] = source_collection.payload
            for item in source_collection.items:
                label = item.effective_name if item and item.effective_name else f"Broń #{item.id}"
                parent_weapon_options.append(
                    {
                        "id": item.id,
                        "name": label,
                        "armory_id": item.armory_id,
                        "armory_name": item.armory.name if item.armory else "",
                    }
                )

    hierarchy_options = [
        item
        for item in parent_weapon_options
        if item.get("armory_id") == armory.id
    ]

    selected_source_id = armory.id
    selected_parent_weapon_id = None
    if weapon and weapon.parent:
        selected_source_id = weapon.parent.armory_id
        selected_parent_weapon_id = weapon.parent_id
    elif armory.parent:
        selected_source_id = armory.parent.id

    current_parent_hint = None
    if weapon and weapon.parent:
        current_parent_hint = {
            "id": weapon.parent.id,
            "name": weapon.parent.effective_name or f"Broń #{weapon.parent.id}",
            "armory_id": weapon.parent.armory_id,
            "armory_name": weapon.parent.armory.name if weapon.parent.armory else "",
        }

    return {
        "source_armories": source_armories,
        "parent_weapon_options": parent_weapon_options,
        "source_weapon_trees": source_weapon_trees,
        "hierarchy_options": hierarchy_options,
        "selected_source_armory_id": selected_source_id,
        "selected_parent_weapon_id": selected_parent_weapon_id,
        "disable_inheritance": bool(armory.parent and weapon and weapon.parent is None),
        "current_parent_hint": current_parent_hint,
    }


def _weapon_descendant_ids(db: Session, root_weapon_id: int) -> set[int]:
    descendants: set[int] = set()
    queue = [root_weapon_id]
    while queue:
        current_id = queue.pop(0)
        children = (
            db.execute(select(models.Weapon.id).where(models.Weapon.parent_id == current_id))
            .scalars()
            .all()
        )
        for child_id in children:
            if child_id in descendants:
                continue
            descendants.add(child_id)
            queue.append(child_id)
    return descendants


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

    source_node_map: dict[int, dict] = {}

    for entry in weapon_rows:
        weapon = entry.get("instance")
        if not weapon or weapon.id is None:
            continue
        node = node_map.get(weapon.id)
        if not node:
            continue
        parent = weapon.parent
        if (
            parent
            and parent.id is not None
            and getattr(parent, "armory_id", None) != weapon.armory_id
        ):
            visited_sources: set[int] = set()
            current = parent
            while current is not None:
                source_id = getattr(current, "id", None)
                if source_id is None or source_id in visited_sources:
                    break
                visited_sources.add(source_id)
                source_node_map.setdefault(source_id, node)
                current = getattr(current, "parent", None)

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
            local_parent: dict | None = None
            parent = weapon.parent
            if parent_id and parent is not None:
                visited_sources: set[int] = set()
                current = parent
                while current is not None:
                    source_id = getattr(current, "id", None)
                    if source_id is None or source_id in visited_sources:
                        break
                    visited_sources.add(source_id)
                    candidate = source_node_map.get(source_id)
                    if candidate and candidate is not node:
                        local_parent = candidate
                        break
                    current = getattr(current, "parent", None)
            if local_parent is not None:
                local_parent.setdefault("children", []).append(node)
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


def _weapon_chain_ids(db: Session, weapon: models.Weapon) -> list[int]:
    ids: list[int] = [weapon.id]
    children = (
        db.execute(select(models.Weapon).where(models.Weapon.parent_id == weapon.id))
        .scalars()
        .all()
    )
    for child in children:
        ids.extend(_weapon_chain_ids(db, child))
    return ids


def _delete_weapon_chain(db: Session, weapon: models.Weapon) -> None:
    children = db.execute(
        select(models.Weapon).where(models.Weapon.parent_id == weapon.id)
    ).scalars().all()
    for child in children:
        _delete_weapon_chain(db, child)
    db.delete(weapon)


def _disable_inherited_weapon(db: Session, armory: models.Armory, weapon: models.Weapon) -> None:
    if not weapon.parent_id:
        return

    exists = (
        db.execute(
            select(models.ArmoryDisabledWeapon).where(
                models.ArmoryDisabledWeapon.armory_id == armory.id,
                models.ArmoryDisabledWeapon.weapon_id == weapon.parent_id,
            )
        )
        .scalar_one_or_none()
        is not None
    )
    if exists:
        return

    db.add(
        models.ArmoryDisabledWeapon(
            armory_id=armory.id,
            weapon_id=weapon.parent_id,
        )
    )


def _cleanup_weapon_references(
    db: Session, armory: models.Armory, weapon_ids: set[int]
) -> None:
    if not weapon_ids:
        return

    armory_ids = set(
        db.execute(
            select(models.Weapon.armory_id).where(models.Weapon.id.in_(weapon_ids))
        ).scalars()
    )
    if not armory_ids:
        armory_ids.add(armory.id)

    db.execute(
        delete(models.UnitWeapon).where(models.UnitWeapon.weapon_id.in_(weapon_ids))
    )
    db.execute(
        delete(models.ArmySpell).where(models.ArmySpell.weapon_id.in_(weapon_ids))
    )

    roster_units = (
        db.execute(
            select(models.RosterUnit)
            .join(models.Roster)
            .join(models.Army)
            .where(models.Army.armory_id.in_(armory_ids))
        )
        .scalars()
        .all()
    )

    for roster_unit in roster_units:
        payload_text = roster_unit.extra_weapons_json
        if not payload_text:
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        weapons_section = payload.get("weapons")
        if not isinstance(weapons_section, dict):
            continue
        updated_section: dict[str, object] = {}
        changed = False
        for key, value in weapons_section.items():
            try:
                weapon_id = int(str(key))
            except (TypeError, ValueError):
                updated_section[str(key)] = value
                continue
            if weapon_id in weapon_ids:
                changed = True
                continue
            updated_section[str(key)] = value
        if changed or len(updated_section) != len(weapons_section):
            payload["weapons"] = updated_section
            roster_unit.extra_weapons_json = json.dumps(payload, ensure_ascii=False)


def _parent_chain(armory: models.Armory) -> list[models.Armory]:
    chain: list[models.Armory] = []
    current = armory.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    return chain


def _sync_descendant_variants(
    db: Session,
    armory: models.Armory,
    protected_weapon_ids: set[int] | None = None,
) -> None:
    stack: list[models.Armory] = list(armory.variants)
    while stack:
        variant = stack.pop()
        utils.ensure_armory_variant_sync(
            db,
            variant,
            protected_weapon_ids=protected_weapon_ids,
        )
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

    selected_weapon_id: int | None = None
    selected_weapon_param = request.query_params.get("selected_weapon")
    if selected_weapon_param:
        try:
            selected_weapon_id = int(selected_weapon_param)
        except (TypeError, ValueError):
            selected_weapon_id = None

    return _render_armory_detail(
        request=request,
        db=db,
        armory=armory,
        current_user=current_user,
        error=None,
        selected_weapon_id=selected_weapon_id,
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
                "warning": None,
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

    new_armory = models.Armory(
        name=cleaned_name,
        owner_id=owner_id,
        parent=source.parent if source.parent_id is not None else None,
    )
    db.add(new_armory)
    db.flush()

    if source.parent_id is not None:
        utils.ensure_armory_variant_sync(db, new_armory)
        db.flush()

        source_weapons = (
            db.execute(select(models.Weapon).where(models.Weapon.armory_id == source.id))
            .scalars()
            .all()
        )
        new_variant_weapons = (
            db.execute(
                select(models.Weapon).where(models.Weapon.armory_id == new_armory.id)
            )
            .scalars()
            .all()
        )
        new_weapons_by_parent = {
            weapon.parent_id: weapon
            for weapon in new_variant_weapons
            if weapon.parent_id is not None
        }

        for weapon in source_weapons:
            if weapon.parent_id is not None:
                clone = new_weapons_by_parent.get(weapon.parent_id)
                if not clone:
                    continue
                for field in OVERRIDABLE_FIELDS:
                    setattr(clone, field, getattr(weapon, field))
                clone.cached_cost = weapon.cached_cost
                continue

            clone = models.Weapon(
                armory=new_armory,
                owner_id=new_armory.owner_id,
                name=weapon.name,
                range=weapon.range,
                attacks=weapon.attacks,
                ap=weapon.ap,
                tags=weapon.tags,
                notes=weapon.notes,
            )
            cached_cost = weapon.cached_cost
            if cached_cost is None:
                cached_cost = costs.weapon_cost(clone)
            clone.cached_cost = cached_cost
            db.add(clone)

        utils.ensure_armory_variant_sync(db, new_armory)
        db.flush()
    else:
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
            "inheritance_panel": _weapon_inheritance_panel_context(db, armory),

            "error": None,
        },
    )


@router.post("/{armory_id}/weapons/new")
def create_weapon(
    armory_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(""),
    attacks: str = Form(""),
    ap: str = Form(""),

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
                "inheritance_panel": _weapon_inheritance_panel_context(db, armory),
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
                "range_options": RANGE_OPTIONS,
                "parent_defaults": None,
                "weapon_abilities": WEAPON_DEFINITION_PAYLOAD,
                "inheritance_panel": _weapon_inheritance_panel_context(db, armory),
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
            "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),

            "error": None,
            "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
        },
    )


@router.post("/{armory_id}/weapons/{weapon_id}/edit")
def update_weapon(
    armory_id: int,
    weapon_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(""),
    attacks: str = Form(""),
    ap: str = Form(""),

    abilities: str | None = Form(None),

    notes: str | None = Form(None),
    inheritance_mode: str | None = Form(None),
    inherit_armory_id: str | None = Form(None),
    inherit_parent_weapon_id: str | None = Form(None),
    placement_parent_id: str | None = Form(None),
    inheritance_source_armory_id: str | None = Form(None),
    inheritance_parent_weapon_id: str | None = Form(None),
    disable_inheritance: str | None = Form(None),
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
                "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),

                "error": "Nazwa broni jest wymagana.",
                "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
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
                "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),

                "error": str(exc),
                "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
            },
        )

    cleaned_range = range.strip()
    tags_text = _serialize_weapon_tags(ability_items)
    cleaned_notes_text = (notes or "").strip()

    original_parent_id = weapon.parent_id
    selected_parent_weapon: models.Weapon | None = None

    if action == "save":
        selected_source_armory_id: int | None = None
        selected_parent_weapon_id: int | None = None
        selected_placement_parent_id: int | None = None

        disable_inheritance_enabled = bool(disable_inheritance)
        if inheritance_mode == "independent":
            disable_inheritance_enabled = True
        elif inheritance_mode == "inherit":
            disable_inheritance_enabled = False

        source_armory_input = (
            inherit_armory_id
            if inherit_armory_id not in (None, "")
            else inheritance_source_armory_id
        )
        inherit_parent_input = (
            inherit_parent_weapon_id
            if inherit_parent_weapon_id not in (None, "")
            else inheritance_parent_weapon_id
        )

        try:
            if source_armory_input not in (None, ""):
                selected_source_armory_id = int(source_armory_input)
            if inherit_parent_input not in (None, ""):
                selected_parent_weapon_id = int(inherit_parent_input)
            if placement_parent_id not in (None, ""):
                selected_placement_parent_id = int(placement_parent_id)
        except ValueError:
            selected_source_armory_id = None
            selected_parent_weapon_id = None
            selected_placement_parent_id = None

        if selected_parent_weapon_id is None:
            selected_parent_weapon_id = selected_placement_parent_id

        parent_chain_ids = {
            item.id for item in [armory, *_parent_chain(armory)] if item.id is not None
        }
        if selected_source_armory_id and selected_source_armory_id not in parent_chain_ids:
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
                    "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                    "error": "Nieprawidłowa zbrojownia źródłowa.",
                    "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                },
            )

        if (
            selected_placement_parent_id is not None
            and selected_placement_parent_id != selected_parent_weapon_id
        ):
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
                    "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                    "error": "Niespójne dane parenta broni.",
                    "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                },
            )

        if not disable_inheritance_enabled and selected_parent_weapon_id is not None:
            selected_parent_weapon = db.get(models.Weapon, selected_parent_weapon_id)
            if selected_parent_weapon is None:
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
                        "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                        "error": "Wybrana broń nadrzędna nie istnieje.",
                        "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                    },
                )
            if selected_parent_weapon.armory_id not in parent_chain_ids:
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
                        "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                        "error": "Wybrana broń nadrzędna nie należy do bieżącej lub nadrzędnej zbrojowni.",
                        "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                    },
                )
            if selected_source_armory_id and selected_parent_weapon.armory_id != selected_source_armory_id:
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
                        "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                        "error": "Broń nadrzędna nie należy do wybranej zbrojowni źródłowej.",
                        "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                    },
                )
            if selected_parent_weapon_id == weapon.id:
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
                        "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                        "error": "Broń nie może dziedziczyć sama po sobie.",
                        "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                    },
                )
            if selected_parent_weapon_id in _weapon_descendant_ids(db, weapon.id):
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
                        "inheritance_panel": _weapon_inheritance_panel_context(db, armory, weapon),
                        "error": "Nie można ustawić potomka jako parenta (blokada cykli).",
                        "cancel_url": f"/armories/{armory.id}?selected_weapon={weapon.id}",
                    },
                )
            weapon.parent_id = selected_parent_weapon_id
        elif disable_inheritance_enabled:
            weapon.parent_id = None

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
        parent = _resolve_local_parent_for_variant(db, armory, weapon)
        protected_parent_id = parent.id
        inherit_as_overrides = armory.parent is not None
        variant_name = (
            None if inherit_as_overrides and cleaned_name == parent.effective_name else cleaned_name
        )
        variant_range = (
            None if inherit_as_overrides and cleaned_range == parent.effective_range else cleaned_range
        )
        variant_attacks_input = (
            attacks_value if attacks_value is not None else parent.effective_attacks
        )
        if inherit_as_overrides and math.isclose(
            variant_attacks_input,
            parent.effective_attacks,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            variant_attacks = None
        else:
            variant_attacks = variant_attacks_input

        variant_ap_input = ap_value if ap_value is not None else parent.effective_ap
        variant_ap = (
            None if inherit_as_overrides and variant_ap_input == parent.effective_ap else variant_ap_input
        )

        cleaned_tags = tags_text or ""
        inherited_tags = parent.effective_tags or ""
        variant_tags = None if inherit_as_overrides and cleaned_tags == inherited_tags else cleaned_tags

        cleaned_notes = cleaned_notes_text or None
        variant_notes = (
            None if inherit_as_overrides and cleaned_notes == parent.effective_notes else cleaned_notes
        )

        if (
            variant_name is None
            and variant_range is None
            and variant_attacks is None
            and variant_ap is None
            and variant_tags is None
            and variant_notes is None
        ):
            existing_weapon = (
                db.execute(
                    select(models.Weapon).where(
                        models.Weapon.armory_id == armory.id,
                        models.Weapon.parent_id == parent.id,
                        models.Weapon.name.is_(None),
                        models.Weapon.range.is_(None),
                        models.Weapon.attacks.is_(None),
                        models.Weapon.ap.is_(None),
                        models.Weapon.tags.is_(None),
                        models.Weapon.notes.is_(None),
                    )
                )
                .scalars()
                .first()
            )
            if existing_weapon:
                target_armory_id = (
                    existing_weapon.armory_id
                    if existing_weapon.armory_id is not None
                    else armory.id
                )
                return RedirectResponse(
                    url=f"/armories/{target_armory_id}/weapons/{existing_weapon.id}/edit",
                    status_code=303,
                )

        new_weapon = models.Weapon(
            armory_id=armory.id,
            owner_id=armory.owner_id,
            parent_id=parent.id,
            army_id=None,
            name=variant_name,
            range=variant_range,
            attacks=variant_attacks,
            ap=variant_ap,
            tags=variant_tags,
            notes=variant_notes,
        )

        _update_weapon_cost(new_weapon)
        db.add(new_weapon)
        db.flush()
        parent_armory_id = new_weapon.parent.armory_id if new_weapon.parent else None
        if parent_armory_id != armory.id:
            logger.warning(
                "Rejecting cross-armory weapon variant: armory_id=%s weapon_id=%s parent_id=%s parent_armory_id=%s",
                armory.id,
                new_weapon.id,
                new_weapon.parent_id,
                parent_armory_id,
            )
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Nie można utworzyć wariantu z rodzicem spoza bieżącej zbrojowni.",
            )
        _sync_descendant_variants(
            db,
            armory,
            protected_weapon_ids={protected_parent_id, new_weapon.id},
        )
        parent_after_sync = db.get(models.Weapon, protected_parent_id)
        new_weapon_after_sync = db.get(models.Weapon, new_weapon.id)
        if (
            parent_after_sync is None
            or new_weapon_after_sync is None
            or new_weapon_after_sync.parent_id != protected_parent_id
        ):
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Naruszenie integralności wariantu: rodzic wariantu został usunięty "
                    "lub relacja parent-child jest niepoprawna."
                ),
            )
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

    cleaned_tags = tags_text or ""
    if weapon.parent:
        inherited_tags = weapon.parent.effective_tags or ""
        weapon.tags = None if cleaned_tags == inherited_tags else cleaned_tags
    else:
        weapon.tags = cleaned_tags or None

    cleaned_notes = cleaned_notes_text or None
    if weapon.parent:
        weapon.notes = None if cleaned_notes == weapon.parent.effective_notes else cleaned_notes
    else:
        weapon.notes = cleaned_notes

    _update_weapon_cost(weapon)

    if action == "save" and weapon.parent_id != original_parent_id:
        protected_weapon_ids = {weapon.id} if weapon.id is not None else set()
        if original_parent_id is not None:
            protected_weapon_ids.add(original_parent_id)
        if weapon.parent_id is not None:
            protected_weapon_ids.add(weapon.parent_id)
        try:
            _sync_descendant_variants(
                db,
                armory,
                protected_weapon_ids=protected_weapon_ids,
            )
            if original_parent_id is not None and db.get(models.Weapon, original_parent_id) is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Naruszenie integralności: zmiana dziedziczenia próbowała usunąć "
                        "poprzedni rekord rodzica."
                    ),
                )
            if weapon.parent_id is not None and db.get(models.Weapon, weapon.parent_id) is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Naruszenie integralności: nowy rekord rodzica został usunięty "
                        "podczas synchronizacji."
                    ),
                )
        except Exception:
            db.rollback()
            raise

    if weapon.id is not None:
        from .armies import _weapon_spell_details

        base_label, description, cost = _weapon_spell_details(weapon)
        linked_spells = (
            db.execute(
                select(models.ArmySpell).where(models.ArmySpell.weapon_id == weapon.id)
            )
            .scalars()
            .all()
        )
        for spell in linked_spells:
            spell.base_label = base_label
            spell.description = description
            spell.cost = cost

    db.commit()
    selected_param = f"?selected_weapon={weapon.id}" if weapon.id is not None else ""
    return RedirectResponse(
        url=f"/armories/{armory.id}{selected_param}", status_code=303
    )


@router.post("/{armory_id}/weapons/{weapon_id}/delete")
def delete_weapon(
    armory_id: int,
    weapon_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    armory = _get_armory(db, armory_id)
    _ensure_armory_edit_access(armory, current_user)
    weapon = _get_weapon(db, armory, weapon_id)

    weapon_ids = set(_weapon_chain_ids(db, weapon))

    default_units = (
        db.execute(
            select(models.Unit)
            .join(models.Army)
            .where(
                models.Unit.default_weapon_id.in_(weapon_ids),
                models.Army.armory_id == armory.id,
            )
        )
        .scalars()
        .all()
    )
    if default_units:
        unit_names = sorted({unit.name for unit in default_units})
        error = (
            "Nie można usunąć broni, jest ustawiona jako domyślna dla jednostek: "
            + ", ".join(unit_names)
        )
        return _render_armory_detail(
            request=request,
            db=db,
            armory=armory,
            current_user=current_user,
            error=error,
            selected_weapon_id=weapon.id,
        )

    _disable_inherited_weapon(db, armory, weapon)
    _cleanup_weapon_references(db, armory, weapon_ids)
    _delete_weapon_chain(db, weapon)
    db.commit()
    return RedirectResponse(url=f"/armories/{armory.id}", status_code=303)
