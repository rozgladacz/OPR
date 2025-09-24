from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..data import abilities as ability_catalog


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
        if link.params_json:
            try:
                data = json.loads(link.params_json)
            except json.JSONDecodeError:
                data = {}
            raw = data.get("value")
            if raw is not None:
                value = str(raw)
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
        params = None
        if value not in (None, ""):
            params = json.dumps({"value": value}, ensure_ascii=False)
        result.append(models.UnitAbility(ability=ability, params_json=params))
    return result
