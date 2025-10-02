from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..data import abilities as ability_catalog

AURA_RANGE_OPTIONS = (6, 12)
ABILITY_NAME_MAX_LENGTH = 60
EXCLUDED_AURA_AND_ORDER_SLUGS: set[str] = {
    "zasadzka",
    "zwiadowca",
    "nieruchomy",
    "samolot",
    "dobrze_strzela",
    "zle_strzela",
    "bohater",
    "transport",
    "masywny",
}


def ability_slug(ability: models.Ability) -> str | None:
    if ability.config_json:
        try:
            data = json.loads(ability.config_json)
        except json.JSONDecodeError:
            data = {}
        slug = data.get("slug")
        if slug:
            return slug
    if ability.name:
        return ability.name.casefold().replace(" ", "_")
    return None


def _ability_config(definition: ability_catalog.AbilityDefinition) -> dict:
    return {
        "slug": definition.slug,
        "value_label": definition.value_label,
        "value_type": definition.value_type,
    }


def sync_definitions(session: Session) -> None:
    existing_by_slug: dict[str, models.Ability] = {}
    existing_by_name: dict[str, models.Ability] = {}
    records: Iterable[models.Ability] = (
        session.execute(select(models.Ability)).scalars().all()
    )
    for ability in records:
        if ability.owner_id not in (None,):
            continue
        slug: str | None = None
        if ability.config_json:
            try:
                data = json.loads(ability.config_json)
            except json.JSONDecodeError:
                data = {}
            slug = data.get("slug")
        if not slug and ability.name:
            slug = ability.name.casefold().replace(" ", "_")
        if slug:
            existing_by_slug[slug] = ability
        if ability.name:
            existing_by_name[ability.name.casefold()] = ability

    for definition in ability_catalog.all_definitions():
        ability = existing_by_slug.get(definition.slug)
        if ability is None:
            ability = existing_by_name.get(definition.display_name().casefold())
        if ability is None:
            ability = models.Ability(
                name=definition.display_name(),
                type=definition.type,
                description=definition.description,
                owner_id=None,
            )
            session.add(ability)
        else:
            ability.name = definition.display_name()
            ability.type = definition.type
            ability.description = definition.description
            ability.owner_id = None
        ability.config_json = json.dumps(
            _ability_config(definition), ensure_ascii=False
        )

    session.flush()


def definition_payload(session: Session, ability_type: str) -> list[dict]:
    sync_definitions(session)
    definitions = ability_catalog.definitions_by_type(ability_type)
    passive_definitions = [
        definition
        for definition in ability_catalog.definitions_by_type("passive")
        if definition.slug not in EXCLUDED_AURA_AND_ORDER_SLUGS
    ]
    records = (
        session.execute(
            select(models.Ability)
            .where(models.Ability.type == ability_type)
            .where(models.Ability.owner_id.is_(None))
        )
        .scalars()
        .all()
    )
    ability_by_slug = {ability_slug(ability): ability for ability in records}
    payload: list[dict] = []
    for definition in definitions:
        entry = ability_catalog.to_dict(definition)
        if definition.slug == "rozkaz":
            entry["value_choices"] = [
                {
                    "value": passive.slug,
                    "label": passive.name,
                    "description": passive.description,
                }
                for passive in passive_definitions
            ]
        elif definition.slug == "aura":
            aura_choices: list[dict] = []
            for passive in passive_definitions:
                for range_value in AURA_RANGE_OPTIONS:
                    prefix = (
                        f"{definition.name}(12\")"
                        if int(range_value) == 12
                        else definition.name
                    )
                    aura_choices.append(
                        {
                            "value": f"{passive.slug}|{range_value}",
                            "label": f"{prefix}: {passive.name}",
                            "description": passive.description,
                        }
                    )
            entry["value_choices"] = aura_choices
        ability = ability_by_slug.get(definition.slug)
        entry["ability_id"] = ability.id if ability else None
        payload.append(entry)
    return payload


def unit_ability_payload(unit: models.Unit, ability_type: str) -> list[dict]:
    items: list[dict] = []
    for link in getattr(unit, "abilities", []):
        ability = link.ability
        if not ability or ability.type != ability_type:
            continue
        slug = ability_slug(ability) or ""
        definition = ability_catalog.find_definition(slug)
        value: str | None = None
        is_default = None
        custom_name: str | None = None
        if link.params_json:
            try:
                data = json.loads(link.params_json)
            except json.JSONDecodeError:
                data = {}
            else:
                raw = data.get("value")
                if raw is not None:
                    value = str(raw)
                if "default" in data:
                    is_default = bool(data["default"])
                elif "is_default" in data:
                    is_default = bool(data["is_default"])
                raw_custom = data.get("custom_name")
                if isinstance(raw_custom, str):
                    custom_name = raw_custom.strip()[:ABILITY_NAME_MAX_LENGTH]
                    if not custom_name:
                        custom_name = None
        label = (
            ability_catalog.display_with_value(definition, value)
            if definition
            else ability.name or slug
        )
        items.append(
            {
                "ability_id": ability.id,
                "slug": slug,
                "value": value or "",
                "label": label,
                "base_label": label,
                "custom_name": custom_name,
                "description": definition.description if definition else "",
                "is_default": bool(is_default) if is_default is not None else False,
            }
        )
    return items


def build_unit_abilities(
    session: Session, payload: list[dict], ability_type: str
) -> list[models.UnitAbility]:
    if not payload:
        return []
    records = (
        session.execute(
            select(models.Ability)
            .where(models.Ability.type == ability_type)
            .where(models.Ability.owner_id.is_(None))
        )
        .scalars()
        .all()
    )
    by_id = {ability.id: ability for ability in records if ability.id is not None}
    by_slug = {ability_slug(ability): ability for ability in records}
    result: list[models.UnitAbility] = []
    for item in payload:
        ability = None
        ability_id = item.get("ability_id")
        if ability_id:
            ability = by_id.get(int(ability_id))
        if ability is None:
            slug = item.get("slug")
            if slug:
                ability = by_slug.get(str(slug))
        if ability is None:
            continue
        value = item.get("value")
        default_flag = item.get("is_default")
        params: dict[str, object] = {}
        if value not in (None, ""):
            params["value"] = value
        if default_flag is not None:
            params["default"] = bool(default_flag)
        raw_custom = item.get("custom_name")
        if isinstance(raw_custom, str):
            custom_name = raw_custom.strip()[:ABILITY_NAME_MAX_LENGTH]
            if custom_name:
                params["custom_name"] = custom_name
        params_json = json.dumps(params, ensure_ascii=False) if params else None
        result.append(models.UnitAbility(ability=ability, params_json=params_json))
    return result
