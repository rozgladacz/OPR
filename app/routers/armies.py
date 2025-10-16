from __future__ import annotations

import json
import math

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..data import abilities as ability_catalog
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs, utils

MAX_ARMY_SPELLS = 6
FORBIDDEN_SPELL_SLUGS = {"mag", "przekaznik"}
FORBIDDEN_SPELL_WEAPON_TRAITS = {
    "impet",
    "zuzywalny",
    "podkrecenie",
    "niezawodny",
    "rozrywajacy",
    "szturmowa",
    "atak_wrecz",
}

SPELL_WEAPON_DEFINITIONS = [
    definition
    for definition in ability_catalog.definitions_by_type("weapon")
    if definition.slug not in FORBIDDEN_SPELL_WEAPON_TRAITS
]
SPELL_WEAPON_DEFINITION_MAP = {
    definition.slug: definition for definition in SPELL_WEAPON_DEFINITIONS
}
SPELL_WEAPON_DEFINITION_PAYLOAD = [
    ability_catalog.to_dict(definition)
    for definition in SPELL_WEAPON_DEFINITIONS
]
SPELL_WEAPON_SYNONYMS = {
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
    "bez oslon": "bez_oslon",
    "bez osłon": "bez_oslon",
    "bez regeneracji": "brutalny",
    "bez regegenracji": "brutalny",
    "no regen": "brutalny",
    "no regeneration": "brutalny",
    "overcharge": "podkrecenie",
    "overclock": "podkrecenie",
}

SPELL_RANGE_OPTIONS = []
for value in sorted(costs.RANGE_TABLE.keys()):
    label = "Wręcz" if value == 0 else f"{value}\""
    SPELL_RANGE_OPTIONS.append({"value": str(value), "label": label})

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


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "on", "yes"}


PASSIVE_DEFINITIONS = sorted(
    (
        entry
        for entry in (
            ability_catalog.to_dict(definition)
            for definition in ability_catalog.definitions_by_type("passive")
        )
        if not _is_hidden_trait(entry.get("slug"))
    ),
    key=lambda entry: entry.get("display_name", "").casefold(),
)


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


def _ordered_army_units(db: Session, army: models.Army) -> list[models.Unit]:
    return (
        db.execute(
            select(models.Unit)
            .where(models.Unit.army_id == army.id)
            .order_by(models.Unit.position, models.Unit.id)
        )
        .scalars()
        .all()
    )


def _clone_army_contents(
    db: Session,
    source: models.Army,
    target: models.Army,
    *,
    link_parent_units: bool,
) -> None:
    unit_owner_id = target.owner_id
    for unit in _ordered_army_units(db, source):
        cloned_unit = models.Unit(
            army=target,
            owner_id=unit_owner_id,
            name=unit.name,
            quality=unit.quality,
            defense=unit.defense,
            toughness=unit.toughness,
            flags=unit.flags,
            default_weapon_id=unit.default_weapon_id,
            position=unit.position,
        )
        if link_parent_units:
            cloned_unit.parent = unit
        db.add(cloned_unit)

        for ability_link in getattr(unit, "abilities", []) or []:
            db.add(
                models.UnitAbility(
                    unit=cloned_unit,
                    ability_id=ability_link.ability_id,
                    params_json=ability_link.params_json,
                )
            )

        for weapon_link in getattr(unit, "weapon_links", []) or []:
            count_raw = getattr(weapon_link, "default_count", None)
            is_default = bool(getattr(weapon_link, "is_default", False))
            try:
                default_count = int(count_raw)
            except (TypeError, ValueError):
                default_count = 1 if is_default else 0
            if default_count < 0:
                default_count = 0
            if not is_default and default_count > 0:
                is_default = True

            db.add(
                models.UnitWeapon(
                    unit=cloned_unit,
                    weapon_id=weapon_link.weapon_id,
                    is_default=is_default,
                    default_count=default_count,
                    position=getattr(weapon_link, "position", 0) or 0,
                )
            )

    spell_weapon_map: dict[int, models.Weapon] = {}
    for spell in list(getattr(source, "spells", []) or []):
        new_weapon: models.Weapon | None = None
        weapon_id = spell.weapon_id
        if spell.kind == "weapon" and spell.weapon_id:
            source_weapon = spell.weapon
            if source_weapon and source_weapon.army_id == source.id:
                new_weapon = spell_weapon_map.get(source_weapon.id)
                if new_weapon is None:
                    new_weapon = models.Weapon(
                        armory=target.armory,
                        army=target,
                        owner_id=target.owner_id,
                        name=source_weapon.name,
                        range=source_weapon.range,
                        attacks=source_weapon.attacks,
                        ap=source_weapon.ap,
                        tags=source_weapon.tags,
                        notes=source_weapon.notes,
                    )
                    new_weapon.cached_cost = source_weapon.cached_cost
                    db.add(new_weapon)
                    spell_weapon_map[source_weapon.id] = new_weapon
                weapon_id = None
        db.add(
            models.ArmySpell(
                army=target,
                kind=spell.kind,
                ability_id=spell.ability_id,
                ability_value=spell.ability_value,
                weapon=new_weapon,
                weapon_id=weapon_id,
                base_label=spell.base_label,
                description=spell.description,
                cost=spell.cost,
                position=spell.position,
                custom_name=spell.custom_name,
            )
        )


def _resequence_army_units(units: list[models.Unit]) -> None:
    for index, unit in enumerate(units):
        unit.position = index


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
            select(models.Weapon).where(
                models.Weapon.armory_id == armory.id,
                models.Weapon.army_id.is_(None),
            )
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


def _normalized_custom_name(value: str | None) -> str:
    if not value:
        return ""
    return value.strip()[: models.ARMY_SPELL_NAME_MAX_LENGTH]


def _next_spell_position(army: models.Army) -> int:
    max_position = 0
    for spell in getattr(army, "spells", []) or []:
        try:
            position = int(getattr(spell, "position", 0) or 0)
        except (TypeError, ValueError):
            position = 0
        if position > max_position:
            max_position = position
    return max_position + 1


def _resequence_spells(army: models.Army) -> None:
    spells = list(getattr(army, "spells", []) or [])
    if not spells:
        return
    for index, spell in enumerate(
        sorted(spells, key=lambda item: ((getattr(item, "position", 0) or 0), getattr(item, "id", 0) or 0)),
        start=1,
    ):
        if spell.position != index:
            spell.position = index


def _format_weapon_trait(trait: str) -> str:
    text = (trait or "").strip()
    if not text:
        return ""
    parts = text.split()
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0].casefold()}({parts[1]})"
    return text.casefold()


def _weapon_spell_base_details(weapon: models.Weapon) -> tuple[str, str]:
    attacks = getattr(weapon, "display_attacks", None)
    if attacks is None:
        attacks = weapon.effective_attacks
        try:
            attacks = int(math.floor(float(attacks)))
        except (TypeError, ValueError):
            attacks = 1
    attacks = int(attacks or 0)
    attack_label = "trafienie" if attacks == 1 else f"{attacks} trafienia"
    range_raw = (weapon.effective_range or "").strip()
    range_label = f"{range_raw}\"" if range_raw else "Wręcz"
    ap_value = int(getattr(weapon, "effective_ap", 0) or 0)
    base_label = f"{attack_label} {range_label} AP{ap_value}"
    traits = [
        _format_weapon_trait(trait)
        for trait in costs.split_traits(getattr(weapon, "effective_tags", None))
    ]
    traits = [trait for trait in traits if trait]
    if traits:
        base_label = f"{base_label} {', '.join(traits)}"

    description_parts: list[str] = []
    name = (weapon.effective_name or "").strip()
    if name:
        description_parts.append(name)
    description_parts.append(f"Zasięg: {range_label}")
    description_parts.append(f"Ataki: {attacks}")
    description_parts.append(f"AP: {ap_value}")
    if traits:
        description_parts.append(f"Cechy: {', '.join(traits)}")
    notes = (weapon.effective_notes or "").strip()
    if notes:
        description_parts.append(notes)
    description = " | ".join(part for part in description_parts if part)
    return base_label.strip(), description.strip()


def _weapon_spell_details(weapon: models.Weapon) -> tuple[str, str, int]:
    base_label, description = _weapon_spell_base_details(weapon)
    cost_value = costs.weapon_cost(weapon, unit_quality=4)
    cost = int(math.ceil(max(cost_value, 0.0) / 7.0))
    return base_label, description, cost


def _ability_spell_details(
    ability: models.Ability, value: str | None
) -> tuple[str, str, int]:
    slug = ability_registry.ability_slug(ability)
    definition = ability_catalog.find_definition(slug) if slug else None
    base_label = ""
    if definition:
        base_label = ability_catalog.display_with_value(definition, value)
    if not base_label:
        base_label = ability.name or slug or ""
    description = ability_catalog.combined_description(
        definition,
        value,
        ability.description if ability else None,
    )
    if ability.cost_hint is not None:
        base_cost = float(ability.cost_hint)
    else:
        base_cost = costs.ability_cost_from_name(ability.name or "", value)
    cost = int(math.ceil(max(base_cost, 0.0) / 15.0))
    return base_label.strip(), description, cost


def _spell_page_context(
    request: Request,
    army: models.Army,
    current_user: models.User,
    db: Session,
    *,
    error: str | None = None,
    info: str | None = None,
) -> dict:
    spells = list(getattr(army, "spells", []) or [])
    spells.sort(key=lambda item: ((getattr(item, "position", 0) or 0), getattr(item, "id", 0) or 0))
    ability_options = [
        entry
        for entry in ability_registry.definition_payload(db, "active")
        if entry.get("ability_id") and entry.get("slug") not in FORBIDDEN_SPELL_SLUGS
    ]
    ability_options.sort(key=lambda entry: (entry.get("display_name") or entry.get("name") or "").casefold())
    remaining_slots = max(0, MAX_ARMY_SPELLS - len(spells))
    return {
        "request": request,
        "user": current_user,
        "army": army,
        "spells": spells,
        "ability_options": ability_options,
        "remaining_slots": remaining_slots,
        "name_max_length": models.ARMY_SPELL_NAME_MAX_LENGTH,
        "passive_definitions": PASSIVE_DEFINITIONS,
        "error": error,
        "info": info,
    }


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


def _spell_parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError as exc:  # pragma: no cover - validation branch
        raise ValueError("Nieprawidłowa wartość liczby ataków") from exc


def _spell_parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:  # pragma: no cover - validation branch
        raise ValueError("Nieprawidłowa wartość AP") from exc


def _spell_trait_base_and_value(trait: str) -> tuple[str, str]:
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


def _spell_weapon_tags_payload(tags_text: str | None) -> list[dict]:
    payload: list[dict] = []
    if not tags_text:
        return payload
    traits = costs.split_traits(tags_text)
    for trait in traits:
        base, value = _spell_trait_base_and_value(trait)
        slug = SPELL_WEAPON_SYNONYMS.get(base, base.replace(" ", "_"))
        if slug in FORBIDDEN_SPELL_WEAPON_TRAITS:
            continue
        definition = SPELL_WEAPON_DEFINITION_MAP.get(slug)
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


def _spell_normalized_trait_slug(item: dict) -> str | None:
    slug = (item.get("slug") or "").strip().casefold()
    if slug and slug != "__custom__":
        return slug
    raw = (item.get("raw") or "").strip()
    if not raw:
        raw = (item.get("label") or "").strip()
    if not raw:
        return None
    base, _ = _spell_trait_base_and_value(raw)
    normalized = SPELL_WEAPON_SYNONYMS.get(base, base.replace(" ", "_"))
    return normalized.casefold() if normalized else base.replace(" ", "_").casefold()


def _filter_spell_weapon_abilities(items: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for entry in items or []:
        slug = (entry.get("slug") or "").strip()
        normalized = _spell_normalized_trait_slug(entry) or ""
        if normalized in FORBIDDEN_SPELL_WEAPON_TRAITS:
            continue
        raw_text = (entry.get("raw") or "").strip()
        filtered.append(
            {
                "slug": slug or "__custom__",
                "value": entry.get("value", ""),
                "label": entry.get("label", ""),
                "raw": raw_text,
                "description": entry.get("description", ""),
            }
        )
    return filtered


def _parse_spell_weapon_ability_payload(text: str | None) -> list[dict]:
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
                "description": item.get("description", ""),
            }
        )
    return result


def _serialize_spell_weapon_tags(items: list[dict]) -> str:
    entries: list[str] = []
    for item in items or []:
        slug = (item.get("slug") or "").strip()
        normalized = _spell_normalized_trait_slug(item) or ""
        if normalized in FORBIDDEN_SPELL_WEAPON_TRAITS:
            continue
        if slug == "__custom__" or not slug:
            raw = (item.get("raw") or "").strip()
            if not raw:
                continue
            entries.append(raw)
            continue
        definition = SPELL_WEAPON_DEFINITION_MAP.get(normalized)
        if not definition:
            continue
        value = item.get("value")
        value_text = str(value).strip() if value is not None else ""
        if definition.value_label and not value_text:
            entries.append(definition.display_name())
        else:
            entries.append(
                ability_catalog.display_with_value(definition, value_text)
            )
    return ", ".join(entries)


def _spell_weapon_form_values(weapon: models.Weapon | None) -> dict:
    if not weapon:
        return {
            "name": "",
            "range": "",
            "attacks": "1",
            "ap": "0",
            "notes": "",
            "abilities": [],
        }
    return {
        "name": weapon.effective_name,
        "range": weapon.effective_range,
        "attacks": str(weapon.display_attacks),
        "ap": str(weapon.effective_ap),
        "notes": weapon.effective_notes or "",
        "abilities": _spell_weapon_tags_payload(weapon.effective_tags),
    }


def _spell_weapon_form_context(
    request: Request,
    army: models.Army,
    user: models.User,
    *,
    weapon: models.Weapon | None,
    form_values: dict,
    error: str | None = None,
    custom_name: str = "",
    allow_custom_name: bool = False,
) -> dict:
    return {
        "request": request,
        "user": user,
        "armory": army.armory,
        "army": army,
        "weapon": weapon,
        "form_values": form_values,
        "range_options": SPELL_RANGE_OPTIONS,
        "parent_defaults": None,
        "weapon_abilities": SPELL_WEAPON_DEFINITION_PAYLOAD,
        "error": error,
        "cancel_url": f"/armies/{army.id}/spells",
        "allow_variants": False,
        "custom_name_field": allow_custom_name,
        "custom_name_value": custom_name,
        "custom_name_max_length": models.ARMY_SPELL_NAME_MAX_LENGTH,
    }


def _unit_weapon_payload(unit: models.Unit | None) -> list[dict]:
    if not unit:
        return []
    payload: list[dict] = []
    seen: set[int] = set()
    primary_id: int | None = None
    if getattr(unit, "default_weapon_id", None):
        primary_id = unit.default_weapon_id
    elif getattr(unit, "default_weapon", None) and getattr(unit.default_weapon, "id", None):
        primary_id = unit.default_weapon.id
    primary_assigned = False
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
        is_primary = False
        if count_value > 0 and primary_id and link.weapon_id == primary_id:
            is_primary = True
            primary_assigned = True
        range_value = costs.normalize_range_value(
            link.weapon.effective_range if link.weapon else None
        )
        category = "ranged" if range_value > 0 else "melee"
        payload.append(
            {
                "weapon_id": link.weapon_id,
                "name": name,
                "is_default": is_default_flag,
                "is_primary": is_primary,
                "count": count_value,
                "range_value": range_value,
                "category": category,
            }
        )
        seen.add(link.weapon_id)
    if (
        getattr(unit, "default_weapon", None)
        and unit.default_weapon_id
        and unit.default_weapon_id not in seen
    ):
        range_value = costs.normalize_range_value(unit.default_weapon.effective_range)
        category = "ranged" if range_value > 0 else "melee"
        payload.append(
            {
                "weapon_id": unit.default_weapon_id,
                "name": unit.default_weapon.effective_name,
                "is_default": True,
                "is_primary": not primary_assigned,
                "count": 1,
                "range_value": range_value,
                "category": category,
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

    def _parse_primary_flag(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "on", "yes"}
        return False

    records: list[dict[str, object]] = []
    seen: set[int] = set()
    primary_assigned: dict[str, bool] = {}
    fallback_index: dict[str, int | None] = {}
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

        range_value = costs.normalize_range_value(weapon.effective_range)
        category = "ranged" if range_value > 0 else "melee"
        if category not in primary_assigned:
            primary_assigned[category] = False
        if category not in fallback_index:
            fallback_index[category] = None

        primary_raw = entry.get("is_primary")
        if primary_raw is None:
            primary_raw = entry.get("primary")
        if primary_raw is None:
            primary_raw = entry.get("is_primary_weapon")
        is_primary = _parse_primary_flag(primary_raw) if count_value > 0 else False
        if is_primary and primary_assigned.get(category):
            is_primary = False
        if is_primary:
            primary_assigned[category] = True
        elif fallback_index.get(category) is None and count_value > 0:
            fallback_index[category] = len(records)

        records.append(
            {
                "weapon": weapon,
                "is_primary": is_primary,
                "count": count_value,
                "category": category,
            }
        )
        seen.add(weapon_id)

    for category, index in fallback_index.items():
        if not primary_assigned.get(category) and index is not None:
            records[index]["is_primary"] = True
            primary_assigned[category] = True

    results: list[tuple[models.Weapon, bool, int]] = []
    for record in records:
        weapon = record["weapon"]
        count_value = int(record["count"])
        is_primary = bool(record.get("is_primary")) and count_value > 0
        results.append((weapon, is_primary, count_value))
    return results


def _normalized_role_slug(slug: str | None) -> str | None:
    if not slug:
        return None
    normalized = costs.ability_identifier(slug)
    if normalized in costs.ROLE_SLUGS:
        return normalized
    text = str(slug).strip()
    while text.endswith(("?", "!")):
        text = text[:-1].strip()
    normalized = costs.ability_identifier(text)
    if normalized in costs.ROLE_SLUGS:
        return normalized
    return None


def _existing_role_entry(unit: models.Unit) -> dict[str, object] | None:
    for entry in utils.passive_flags_to_payload(getattr(unit, "flags", None)):
        slug = _normalized_role_slug(entry.get("slug"))
        if not slug:
            continue
        return {
            "slug": slug,
            "is_default": bool(entry.get("is_default", True)),
        }
    return None


def _infer_unit_role_slug(unit: models.Unit) -> str | None:
    roster_unit = models.RosterUnit(unit=unit, count=1)
    totals = costs.roster_unit_role_totals(roster_unit)
    warrior = float(totals.get("wojownik") or 0.0)
    shooter = float(totals.get("strzelec") or 0.0)
    if warrior <= 0.0 and shooter <= 0.0:
        return None
    if shooter > warrior:
        return "strzelec"
    if warrior > shooter:
        return "wojownik"
    for weapon, count in unit.default_weapon_loadout:
        if not weapon or count <= 0:
            continue
        try:
            range_value = costs.normalize_range_value(weapon.effective_range)
        except Exception:  # pragma: no cover - fallback for unexpected data
            range_value = 0
        if range_value > 0:
            return "strzelec"
    return "wojownik"


def _apply_unit_form_data(
    unit: models.Unit,
    *,
    name: str,
    quality: int,
    defense: int,
    toughness: int,
    passive_items: list[dict],
    active_items: list[dict],
    aura_items: list[dict],
    weapon_entries: list[tuple[models.Weapon, bool, int]],
    db: Session,
) -> None:
    existing_role = _existing_role_entry(unit)

    sanitized_passives: list[dict] = []
    payload_role: dict[str, object] | None = None
    for item in passive_items:
        if not isinstance(item, dict):
            continue
        slug_text = str(item.get("slug") or "").strip()
        if not slug_text:
            continue
        normalized_role = _normalized_role_slug(slug_text)
        if normalized_role:
            payload_role = {
                "slug": normalized_role,
                "is_default": bool(item.get("is_default", True)),
            }
            continue
        entry = dict(item)
        entry["slug"] = slug_text
        sanitized_passives.append(entry)

    unit.name = name
    unit.quality = quality
    unit.defense = defense
    unit.toughness = toughness
    unit.flags = utils.passive_payload_to_flags(sanitized_passives)

    weapon_links: list[models.UnitWeapon] = []
    default_assigned = False
    fallback_weapon = None
    # weapon_entries contain (weapon, is_primary, default_count) tuples
    for weapon, is_primary, count in weapon_entries:
        weapon_id = getattr(weapon, "id", None)
        link = models.UnitWeapon(
            weapon=weapon,
            weapon_id=weapon_id,
            is_default=count > 0,
            default_count=count,
        )
        weapon_links.append(link)
        if fallback_weapon is None and count > 0:
            fallback_weapon = weapon
        if is_primary and count > 0 and not default_assigned:
            unit.default_weapon = weapon
            default_assigned = True
    for index, link in enumerate(weapon_links):
        link.position = index
    if not default_assigned:
        unit.default_weapon = fallback_weapon
    unit.weapon_links = weapon_links

    ability_links = (
        ability_registry.build_unit_abilities(db, active_items, "active")
        + ability_registry.build_unit_abilities(db, aura_items, "aura")
    )
    for index, link in enumerate(ability_links):
        link.position = index
    unit.abilities = ability_links

    role_entry = payload_role or existing_role
    if role_entry is None:
        inferred_slug = _infer_unit_role_slug(unit)
        if inferred_slug:
            role_entry = {"slug": inferred_slug, "is_default": True}

    if role_entry:
        final_passives = list(sanitized_passives) + [role_entry]
    else:
        final_passives = sanitized_passives

    unit.flags = utils.passive_payload_to_flags(final_passives)


@router.get("", response_class=HTMLResponse)
def list_armies(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    query = (
        select(models.Army)
        .options(
            selectinload(models.Army.units),
            selectinload(models.Army.owner),
        )
        .order_by(models.Army.name)
    )
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


@router.post("/{army_id}/takeover")
def takeover_army(
    army_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Brak uprawnień do przejęcia armii",
        )
    army.owner_id = None
    db.commit()
    return RedirectResponse(url="/armies", status_code=303)


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
            "is_global": False,
            "error": None,
        },
    )


@router.post("/new")
def create_army(
    request: Request,
    name: str = Form(...),
    armory_id: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    ruleset = _get_default_ruleset(db)
    if not ruleset:
        raise HTTPException(status_code=404)
    is_global_flag = _parse_bool(is_global)
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
                "is_global": is_global_flag,
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
                "is_global": is_global_flag,
                "error": "Brak uprawnień do wybranej zbrojowni.",
            },
        )

    if is_global_flag and armory.owner_id is not None:
        armories = _available_armories(db, current_user)
        selected_id = armory.id if armory else (armories[0].id if armories else None)
        return templates.TemplateResponse(
            "army_form.html",
            {
                "request": request,
                "user": current_user,
                "default_ruleset": ruleset,
                "army": None,
                "armories": armories,
                "selected_armory_id": selected_id,
                "is_global": is_global_flag,
                "error": "Globalna armia wymaga globalnej zbrojowni.",
            },
        )

    owner_id = current_user.id
    if is_global_flag:
        if not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Tylko administrator może tworzyć globalne armie",
            )
        owner_id = None

    army = models.Army(
        name=name,
        ruleset=ruleset,
        owner_id=owner_id,
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
    army = (
        db.execute(
            select(models.Army)
            .options(
                selectinload(models.Army.armory),
                selectinload(models.Army.units).options(
                    selectinload(models.Unit.weapon_links)
                    .selectinload(models.UnitWeapon.weapon),
                    selectinload(models.Unit.default_weapon),
                    selectinload(models.Unit.abilities)
                    .selectinload(models.UnitAbility.ability),
                ),
            )
            .where(models.Army.id == army_id)
        )
        .scalars()
        .first()
    )
    if army is None:
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

    weapon_choices = []
    for weapon in weapons:
        range_value = costs.normalize_range_value(weapon.effective_range)
        category = "ranged" if range_value > 0 else "melee"
        weapon_choices.append(
            {
                "id": weapon.id,
                "name": weapon.effective_name,
                "range_value": range_value,
                "category": category,
            }
        )
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


@router.post("/{army_id}/copy")
def copy_army(
    army_id: int,
    name: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    source = db.get(models.Army, army_id)
    if not source:
        raise HTTPException(status_code=404)
    _ensure_army_view_access(source, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nazwa kopii jest wymagana")

    owner_id = current_user.id
    if _parse_bool(is_global):
        if not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Tylko administrator może tworzyć globalne armie",
            )
        owner_id = None

    new_army = models.Army(
        name=cleaned_name,
        owner_id=owner_id,
        ruleset=source.ruleset,
        armory=source.armory,
    )
    db.add(new_army)
    db.flush()

    _clone_army_contents(db, source, new_army, link_parent_units=False)
    db.commit()

    return RedirectResponse(url=f"/armies/{new_army.id}", status_code=303)


@router.post("/{army_id}/variant")
def create_army_variant(
    army_id: int,
    name: str = Form(...),
    is_global: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    base_army = db.get(models.Army, army_id)
    if not base_army:
        raise HTTPException(status_code=404)
    _ensure_army_view_access(base_army, current_user)

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nazwa wariantu jest wymagana")

    owner_id = current_user.id
    if _parse_bool(is_global):
        if not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Tylko administrator może tworzyć globalne armie",
            )
        owner_id = None

    variant = models.Army(
        name=cleaned_name,
        owner_id=owner_id,
        ruleset=base_army.ruleset,
        armory=base_army.armory,
        parent=base_army,
    )
    db.add(variant)
    db.flush()

    _clone_army_contents(db, base_army, variant, link_parent_units=True)
    db.commit()

    return RedirectResponse(url=f"/armies/{variant.id}", status_code=303)


@router.get("/{army_id}/spells", response_class=HTMLResponse)
def edit_army_spells(
    army_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    return templates.TemplateResponse(
        "army_spells.html",
        _spell_page_context(request, army, current_user, db),
    )


def _validate_spell_capacity(
    army: models.Army, request: Request, current_user: models.User, db: Session
):
    if len(getattr(army, "spells", []) or []) >= MAX_ARMY_SPELLS:
        context = _spell_page_context(
            request,
            army,
            current_user,
            db,
            error="Osiągnięto maksymalną liczbę mocy.",
        )
        return templates.TemplateResponse(
            "army_spells.html", context, status_code=400
        )
    return None


@router.get("/{army_id}/spells/weapons/new", response_class=HTMLResponse)
def new_spell_weapon_form(
    army_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    capacity_response = _validate_spell_capacity(army, request, current_user, db)
    if capacity_response is not None:
        return capacity_response

    return templates.TemplateResponse(
        "armory_weapon_form.html",
        _spell_weapon_form_context(
            request,
            army,
            current_user,
            weapon=None,
            form_values=_spell_weapon_form_values(None),
            allow_custom_name=True,
        ),
    )


@router.post("/{army_id}/spells/weapons/new")
def create_spell_weapon(
    army_id: int,
    request: Request,
    name: str = Form(...),
    range: str = Form(""),
    attacks: str = Form("1"),
    ap: str = Form("0"),
    abilities: str | None = Form(None),
    notes: str | None = Form(None),
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    capacity_response = _validate_spell_capacity(army, request, current_user, db)
    if capacity_response is not None:
        return capacity_response

    ability_items = _filter_spell_weapon_abilities(
        _parse_spell_weapon_ability_payload(abilities)
    )
    form_values = {
        "name": name,
        "range": range,
        "attacks": attacks,
        "ap": ap,
        "notes": notes or "",
        "abilities": ability_items,
    }
    cleaned_name = name.strip()
    if not cleaned_name:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            _spell_weapon_form_context(
                request,
                army,
                current_user,
                weapon=None,
                form_values=form_values,
                error="Nazwa broni jest wymagana.",
                custom_name=custom_name or "",
                allow_custom_name=True,
            ),
            status_code=400,
        )

    try:
        attacks_value = _spell_parse_optional_float(attacks)
        ap_value = _spell_parse_optional_int(ap)
    except ValueError as exc:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            _spell_weapon_form_context(
                request,
                army,
                current_user,
                weapon=None,
                form_values=form_values,
                error=str(exc),
                custom_name=custom_name or "",
                allow_custom_name=True,
            ),
            status_code=400,
        )

    if attacks_value is None:
        attacks_value = 1.0
    if ap_value is None:
        ap_value = 0

    cleaned_range = range.strip()
    tags_text = _serialize_spell_weapon_tags(ability_items)
    cleaned_notes = (notes or "").strip()

    weapon = models.Weapon(
        armory=army.armory,
        army=army,
        owner_id=army.owner_id,
        name=cleaned_name,
        range=cleaned_range,
        attacks=attacks_value,
        ap=ap_value,
        tags=tags_text or None,
        notes=cleaned_notes or None,
    )
    weapon.cached_cost = costs.weapon_cost(weapon)
    db.add(weapon)

    base_label, description, cost = _weapon_spell_details(weapon)
    custom_text = _normalized_custom_name(custom_name)
    spell = models.ArmySpell(
        army=army,
        kind="weapon",
        weapon=weapon,
        base_label=base_label,
        description=description,
        cost=cost,
        position=_next_spell_position(army),
        custom_name=custom_text or None,
    )
    db.add(spell)
    _resequence_spells(army)
    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


def _get_spell_weapon(
    db: Session, army: models.Army, weapon_id: int
) -> models.Weapon:
    weapon = db.get(models.Weapon, weapon_id)
    if not weapon or weapon.army_id != army.id:
        raise HTTPException(status_code=404)
    return weapon


@router.get(
    "/{army_id}/spells/weapons/{weapon_id}/edit", response_class=HTMLResponse
)
def edit_spell_weapon_form(
    army_id: int,
    weapon_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    weapon = _get_spell_weapon(db, army, weapon_id)

    return templates.TemplateResponse(
        "armory_weapon_form.html",
        _spell_weapon_form_context(
            request,
            army,
            current_user,
            weapon=weapon,
            form_values=_spell_weapon_form_values(weapon),
        ),
    )


@router.post("/{army_id}/spells/weapons/{weapon_id}/edit")
def update_spell_weapon(
    army_id: int,
    weapon_id: int,
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
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)
    weapon = _get_spell_weapon(db, army, weapon_id)

    ability_items = _filter_spell_weapon_abilities(
        _parse_spell_weapon_ability_payload(abilities)
    )
    form_values = {
        "name": name,
        "range": range,
        "attacks": attacks,
        "ap": ap,
        "notes": notes or "",
        "abilities": ability_items,
    }

    cleaned_name = name.strip()
    if not cleaned_name:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            _spell_weapon_form_context(
                request,
                army,
                current_user,
                weapon=weapon,
                form_values=form_values,
                error="Nazwa broni jest wymagana.",
            ),
            status_code=400,
        )

    try:
        attacks_value = _spell_parse_optional_float(attacks)
        ap_value = _spell_parse_optional_int(ap)
    except ValueError as exc:
        return templates.TemplateResponse(
            "armory_weapon_form.html",
            _spell_weapon_form_context(
                request,
                army,
                current_user,
                weapon=weapon,
                form_values=form_values,
                error=str(exc),
            ),
            status_code=400,
        )

    if attacks_value is None:
        attacks_value = weapon.attacks if weapon.attacks is not None else 1.0
    if ap_value is None:
        ap_value = weapon.ap if weapon.ap is not None else 0

    cleaned_range = range.strip()
    tags_text = _serialize_spell_weapon_tags(ability_items)
    cleaned_notes = (notes or "").strip()

    weapon.name = cleaned_name
    weapon.range = cleaned_range
    weapon.attacks = attacks_value
    weapon.ap = ap_value
    weapon.tags = tags_text or None
    weapon.notes = cleaned_notes or None
    weapon.owner_id = army.owner_id
    weapon.army = army
    weapon.armory = army.armory
    weapon.cached_cost = costs.weapon_cost(weapon)

    base_label, description, cost = _weapon_spell_details(weapon)
    linked_spells = (
        db.execute(
            select(models.ArmySpell)
            .where(models.ArmySpell.army_id == army.id)
            .where(models.ArmySpell.weapon_id == weapon.id)
        )
        .scalars()
        .all()
    )
    for spell in linked_spells:
        spell.base_label = base_label
        spell.description = description
        spell.cost = cost

    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


@router.post("/{army_id}/spells/add-ability")
def add_army_spell_ability(
    army_id: int,
    request: Request,
    ability_id: int = Form(...),
    ability_value: str | None = Form(None),
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    capacity_response = _validate_spell_capacity(army, request, current_user, db)
    if capacity_response is not None:
        return capacity_response

    ability = db.get(models.Ability, ability_id)
    if not ability or ability.type != "active":
        context = _spell_page_context(
            request,
            army,
            current_user,
            db,
            error="Nieprawidłowa zdolność.",
        )
        return templates.TemplateResponse("army_spells.html", context, status_code=400)

    slug = ability_registry.ability_slug(ability)
    if slug in FORBIDDEN_SPELL_SLUGS:
        context = _spell_page_context(
            request,
            army,
            current_user,
            db,
            error="Zdolność nie może być użyta jako moc.",
        )
        return templates.TemplateResponse("army_spells.html", context, status_code=400)

    definition = ability_catalog.find_definition(slug) if slug else None
    requires_value = bool(definition and definition.value_label)
    raw_value = (ability_value or "").strip()
    if requires_value and not raw_value:
        context = _spell_page_context(
            request,
            army,
            current_user,
            db,
            error="Zdolność wymaga podania wartości.",
        )
        return templates.TemplateResponse("army_spells.html", context, status_code=400)

    if definition and definition.value_choices:
        valid_values: set[str] = set()
        for choice in definition.value_choices:
            if isinstance(choice, dict):
                choice_value = choice.get("value")
            else:
                choice_value = choice
            if choice_value is not None:
                valid_values.add(str(choice_value))
        if valid_values and raw_value and raw_value not in valid_values:
            context = _spell_page_context(
                request,
                army,
                current_user,
                db,
                error="Wybrano nieprawidłową wartość zdolności.",
            )
            return templates.TemplateResponse(
                "army_spells.html", context, status_code=400
            )

    value_text = raw_value[:120] if raw_value else None
    base_label, description, cost = _ability_spell_details(ability, value_text)
    custom_text = _normalized_custom_name(custom_name)
    spell = models.ArmySpell(
        army=army,
        kind="ability",
        ability=ability,
        ability_value=value_text,
        base_label=base_label,
        description=description,
        cost=cost,
        position=_next_spell_position(army),
        custom_name=custom_text or None,
    )
    db.add(spell)
    _resequence_spells(army)
    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


@router.post("/{army_id}/spells/add-weapon")
def add_army_spell_weapon(
    army_id: int,
    request: Request,
    weapon_id: int = Form(...),
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    capacity_response = _validate_spell_capacity(army, request, current_user, db)
    if capacity_response is not None:
        return capacity_response

    weapon = db.get(models.Weapon, weapon_id)
    if not weapon or weapon.armory_id != army.armory_id:
        context = _spell_page_context(
            request,
            army,
            current_user,
            db,
            error="Nieprawidłowa broń.",
        )
        return templates.TemplateResponse("army_spells.html", context, status_code=400)

    base_label, description, cost = _weapon_spell_details(weapon)
    custom_text = _normalized_custom_name(custom_name)
    spell = models.ArmySpell(
        army=army,
        kind="weapon",
        weapon=weapon,
        base_label=base_label,
        description=description,
        cost=cost,
        position=_next_spell_position(army),
        custom_name=custom_text or None,
    )
    db.add(spell)
    _resequence_spells(army)
    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


@router.post("/{army_id}/spells/{spell_id}/update")
def update_army_spell(
    army_id: int,
    spell_id: int,
    request: Request,
    custom_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    spell = db.get(models.ArmySpell, spell_id)
    if not spell or spell.army_id != army.id:
        raise HTTPException(status_code=404)

    custom_text = _normalized_custom_name(custom_name)
    spell.custom_name = custom_text or None
    _resequence_spells(army)
    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


@router.post("/{army_id}/spells/{spell_id}/delete")
def delete_army_spell(
    army_id: int,
    spell_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    if not army:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    spell = db.get(models.ArmySpell, spell_id)
    if not spell or spell.army_id != army.id:
        raise HTTPException(status_code=404)

    weapon = spell.weapon
    db.delete(spell)
    db.flush()
    if weapon and weapon.army_id == army.id:
        remaining = db.execute(
            select(models.ArmySpell.id).where(models.ArmySpell.weapon_id == weapon.id)
        ).first()
        if not remaining:
            db.delete(weapon)
    db.refresh(army, attribute_names=["spells"])
    _resequence_spells(army)
    db.commit()
    return RedirectResponse(
        url=f"/armies/{army.id}/spells",
        status_code=303,
    )


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

    unit = models.Unit(
        army=army,
        owner_id=army.owner_id if army.owner_id is not None else current_user.id,
    )
    max_position = (
        db.execute(
            select(func.max(models.Unit.position)).where(models.Unit.army_id == army.id)
        ).scalar_one_or_none()
        or -1
    )
    unit.position = max_position + 1
    _apply_unit_form_data(
        unit,
        name=name,
        quality=quality,
        defense=defense,
        toughness=toughness,
        passive_items=passive_items,
        active_items=active_items,
        aura_items=aura_items,
        weapon_entries=weapon_entries,
        db=db,
    )
    db.add(unit)
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)


@router.post("/{army_id}/units/{unit_id}/move")
def move_army_unit(
    army_id: int,
    unit_id: int,
    direction: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    normalized_direction = (direction or "").strip().lower()
    if normalized_direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Nieprawidłowy kierunek")

    units = _ordered_army_units(db, army)
    try:
        index = next(i for i, item in enumerate(units) if item.id == unit.id)
    except StopIteration:
        raise HTTPException(status_code=404) from None

    target_index = index
    if normalized_direction == "up" and index > 0:
        target_index = index - 1
    elif normalized_direction == "down" and index < len(units) - 1:
        target_index = index + 1

    if target_index != index:
        item = units.pop(index)
        units.insert(target_index, item)
        _resequence_army_units(units)
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

    weapon_choices = []
    for weapon in weapons:
        range_value = costs.normalize_range_value(weapon.effective_range)
        category = "ranged" if range_value > 0 else "melee"
        weapon_choices.append(
            {
                "id": weapon.id,
                "name": weapon.effective_name,
                "range_value": range_value,
                "category": category,
            }
        )
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
    submit_action: str = Form("save"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user()),
):
    army = db.get(models.Army, army_id)
    unit = db.get(models.Unit, unit_id)
    if not army or not unit or unit.army_id != army.id:
        raise HTTPException(status_code=404)
    _ensure_army_edit_access(army, current_user)

    weapon_entries = _parse_weapon_payload(db, army.armory, weapons)
    passive_items = _parse_selection_payload(passive_abilities)
    active_items = _parse_selection_payload(active_abilities)
    aura_items = _parse_selection_payload(aura_abilities)

    normalized_action = (submit_action or "save").strip().lower()
    if normalized_action == "new":
        new_unit = models.Unit(
            army=army,
            owner_id=army.owner_id if army.owner_id is not None else current_user.id,
        )
        max_position = (
            db.execute(
                select(func.max(models.Unit.position)).where(models.Unit.army_id == army.id)
            ).scalar_one_or_none()
            or -1
        )
        new_unit.position = max_position + 1
        _apply_unit_form_data(
            new_unit,
            name=name,
            quality=quality,
            defense=defense,
            toughness=toughness,
            passive_items=passive_items,
            active_items=active_items,
            aura_items=aura_items,
            weapon_entries=weapon_entries,
            db=db,
        )
        db.add(new_unit)
    else:
        _apply_unit_form_data(
            unit,
            name=name,
            quality=quality,
            defense=defense,
            toughness=toughness,
            passive_items=passive_items,
            active_items=active_items,
            aura_items=aura_items,
            weapon_entries=weapon_entries,
            db=db,
        )

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
    db.flush()
    remaining_units = _ordered_army_units(db, army)
    _resequence_army_units(remaining_units)
    db.commit()
    return RedirectResponse(url=f"/armies/{army_id}", status_code=303)
