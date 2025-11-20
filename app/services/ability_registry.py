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
    "strach",
    "waagh",
    "odrodzenie",
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


_SYNC_CACHE_KEY = "_definitions_synced"
_PAYLOAD_CACHE_KEY = "_definition_payload_cache"
_ABILITY_LOOKUP_CACHE_KEY = "_ability_lookup_cache"


def _session_info(session: Session) -> dict:
    info = getattr(session, "info", None)
    if info is None:
        info = {}
        setattr(session, "info", info)
    return info


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
    info = _session_info(session)
    info.pop(_PAYLOAD_CACHE_KEY, None)
    info.pop(_ABILITY_LOOKUP_CACHE_KEY, None)
    _mark_definitions_synced(session)


def _get_definition_payload_cache(session: Session) -> dict[str, list[dict]]:
    info = _session_info(session)
    return info.setdefault(_PAYLOAD_CACHE_KEY, {})


def _mark_definitions_synced(session: Session) -> None:
    _session_info(session)[_SYNC_CACHE_KEY] = True


def definition_payload(session: Session, ability_type: str) -> list[dict]:
    cache = _get_definition_payload_cache(session)
    info = _session_info(session)
    if info.get(_SYNC_CACHE_KEY):
        cached_payload = cache.get(ability_type)
        if cached_payload is not None:
            return cached_payload
    else:
        sync_definitions(session)
        cache = _get_definition_payload_cache(session)
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
        entry["value_kind"] = None
        if definition.slug == "rozkaz":
            entry["value_choices"] = [
                {
                    "value": passive.slug,
                    "label": passive.name,
                    "description": passive.description,
                }
                for passive in passive_definitions
            ]
            entry["value_kind"] = "passive"
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
            entry["value_kind"] = "passive"
        ability = ability_by_slug.get(definition.slug)
        entry["ability_id"] = ability.id if ability else None
        payload.append(entry)
    cache[ability_type] = payload
    return payload


def clear_definition_payload_cache(session: Session) -> None:
    """Invalidate cached ability definitions for the current session."""

    info = _session_info(session)
    info[_SYNC_CACHE_KEY] = False
    info.pop(_PAYLOAD_CACHE_KEY, None)
    info.pop(_ABILITY_LOOKUP_CACHE_KEY, None)


def _get_ability_lookup_maps(
    session: Session, ability_type: str
) -> tuple[dict[int, models.Ability], dict[str, models.Ability]]:
    info = _session_info(session)
    cache = info.setdefault(_ABILITY_LOOKUP_CACHE_KEY, {})
    cached = cache.get(ability_type)
    if cached is None:
        records = (
            session.execute(
                select(models.Ability)
                .where(models.Ability.type == ability_type)
                .where(models.Ability.owner_id.is_(None))
            )
            .scalars()
            .all()
        )
        by_id = {
            ability.id: ability for ability in records if ability.id is not None
        }
        by_slug = {
            slug: ability
            for ability in records
            if (slug := ability_slug(ability))
        }
        cached = (by_id, by_slug)
        cache[ability_type] = cached
    return cached


def unit_ability_payload(unit: models.Unit, ability_type: str) -> list[dict]:
    items: list[dict] = []
    links = [
        link
        for link in getattr(unit, "abilities", [])
        if link.ability and link.ability.type == ability_type
    ]
    links.sort(
        key=lambda link: (
            getattr(link, "position", 0),
            getattr(link, "id", 0) or 0,
        )
    )
    for link in links:
        ability = link.ability
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
        description = ability_catalog.combined_description(
            definition,
            value,
            ability.description if ability else None,
        )
        items.append(
            {
                "ability_id": ability.id,
                "slug": slug,
                "value": value or "",
                "label": label,
                "base_label": label,
                "custom_name": custom_name,
                "description": description,
                "is_default": bool(is_default) if is_default is not None else False,
            }
        )
    return items


def build_unit_abilities(
    session: Session, payload: list[dict], ability_type: str
) -> list[models.UnitAbility]:
    if not payload:
        return []
    by_id, by_slug = _get_ability_lookup_maps(session, ability_type)
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
