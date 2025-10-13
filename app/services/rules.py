from __future__ import annotations

import math
import json
from dataclasses import dataclass
from typing import Iterable, List

from .. import models
from ..data import abilities as ability_catalog
from . import ability_registry, costs


@dataclass
class UnitSummary:
    """Light-weight snapshot of a roster entry used for soft validation."""

    name: str
    models: int
    total_cost: float
    active_count: int
    has_aura: bool
    hero_models: int


def _unit_is_hero(
    unit: models.Unit, roster_unit: models.RosterUnit | None = None
) -> bool:
    for link in _sorted_ability_links(unit):
        ability = getattr(link, "ability", None)
        if not ability:
            continue
        slug = ability_registry.ability_slug(ability)
        if not slug and ability.name:
            slug = ability_catalog.slug_for_name(ability.name)
        if slug == "bohater":
            return True
    passive_state = costs.compute_passive_state(
        unit, getattr(roster_unit, "extra_weapons_json", None)
    )
    for trait in passive_state.traits:
        if costs.ability_identifier(trait) == "bohater":
            return True
    return False


def _parse_ability_counts(roster_unit: models.RosterUnit, section: str) -> dict[int, int]:
    raw_payload = getattr(roster_unit, "extra_weapons_json", None)
    if not raw_payload:
        return {}
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    raw_section = data.get(section)
    if isinstance(raw_section, dict):
        iterable = raw_section.items()
    elif isinstance(raw_section, list):
        iterable = []
        for entry in raw_section:
            if not isinstance(entry, dict):
                continue
            key = (
                entry.get("loadout_key")
                or entry.get("key")
                or entry.get("id")
                or entry.get("ability_id")
            )
            if key is None:
                continue
            iterable.append((key, entry.get("count") or entry.get("per_model")))
    else:
        return {}
    counts: dict[int, int] = {}
    for raw_id, raw_value in iterable:
        raw_id_str = str(raw_id)
        base_id = raw_id_str.split(":", 1)[0]
        try:
            ability_id = int(base_id)
        except (TypeError, ValueError):
            try:
                ability_id = int(float(base_id))
            except (TypeError, ValueError):
                continue
        try:
            count_value = int(raw_value)
        except (TypeError, ValueError):
            try:
                count_value = int(float(raw_value))
            except (TypeError, ValueError):
                count_value = 0
        if count_value > 0:
            counts[ability_id] = count_value
    return counts


def _active_count(roster_unit: models.RosterUnit) -> int:
    counts = _parse_ability_counts(roster_unit, "active")
    if counts:
        return sum(1 for value in counts.values() if value > 0)
    unit = getattr(roster_unit, "unit", None)
    if unit is None:
        return 0
    payload = ability_registry.unit_ability_payload(unit, "active")
    return sum(1 for entry in payload if entry.get("is_default"))


def _has_aura(unit: models.Unit) -> bool:
    return any(
        getattr(getattr(link, "ability", None), "type", "").casefold() == "aura"
        for link in _sorted_ability_links(unit)
    )


def _summaries(roster: models.Roster) -> Iterable[UnitSummary]:
    for roster_unit in getattr(roster, "roster_units", []):
        unit = getattr(roster_unit, "unit", None)
        if unit is None:
            continue
        models_count = getattr(roster_unit, "models", None)
        if models_count is None:
            try:
                models_count = int(getattr(roster_unit, "count", 1))
            except (TypeError, ValueError):
                models_count = 1
        models_count = max(models_count, 0)
        cost_value = getattr(roster_unit, "cached_cost", None)
        if cost_value is None:
            cost_value = costs.roster_unit_cost(roster_unit)
        total_cost = float(cost_value)
        active_cnt = _active_count(roster_unit)
        summary = UnitSummary(
            name=getattr(unit, "name", "Jednostka"),
            models=models_count,
            total_cost=total_cost,
            active_count=active_cnt,
            has_aura=_has_aura(unit),
            hero_models=models_count if _unit_is_hero(unit, roster_unit) else 0,
        )
        yield summary


def collect_roster_warnings(
    roster: models.Roster, total_cost: float | None = None
) -> List[str]:
    config = costs.default_ruleset_config()
    warnings_cfg = config.get("warnings", {}) if isinstance(config, dict) else {}

    max_models = int(warnings_cfg.get("max_models", 21) or 21)
    min_unit_cost = float(warnings_cfg.get("min_unit_cost", 50) or 50)
    max_share = float(warnings_cfg.get("max_share", 0.35) or 0.35)
    heroes_per_points = int(warnings_cfg.get("heroes_per_points", 500) or 500)

    if total_cost is None:
        total_cost = float(costs.roster_total(roster))
    else:
        total_cost = float(total_cost)
    points_limit = 0.0
    try:
        raw_limit = getattr(roster, "points_limit", 0)
        if raw_limit:
            points_limit = float(raw_limit)
    except (TypeError, ValueError):
        points_limit = 0.0
    effective_total = total_cost
    if points_limit and points_limit > effective_total:
        effective_total = points_limit
    summaries = list(_summaries(roster))

    warnings: List[str] = []

    for summary in summaries:
        if summary.active_count > 1:
            warnings.append(
                f"[ACTIVE] Jednostka '{summary.name}' ma więcej niż jedną zdolność aktywną."
            )
        if summary.models > max_models:
            warnings.append(
                f"[SIZE] Jednostka '{summary.name}' ma {summary.models} modeli (> {max_models})."
            )
        if effective_total > 0:
            share = summary.total_cost / effective_total
            if share > max_share:
                warnings.append(
                    f"[LIMIT] '{summary.name}' kosztuje {summary.total_cost:.0f} pkt (> {int(max_share * 100)}% całości)."
                )
            if summary.hero_models <= 0 and summary.total_cost < min_unit_cost:
                warnings.append(
                    f"[LIMIT] '{summary.name}' kosztuje {summary.total_cost:.0f} pkt (< {int(min_unit_cost)} pkt)."
                )

    if heroes_per_points > 0:
        hero_models = sum(item.hero_models for item in summaries)
        reference_points = points_limit if points_limit > 0 else total_cost
        if reference_points <= 0:
            allowed = 1
        else:
            allowed = max(1, math.ceil(reference_points / heroes_per_points))
        if hero_models > allowed:
            warnings.append(
                f"[HERO] Bohaterów {hero_models}, standard: ≤ {allowed} (1/{heroes_per_points} pkt)."
            )

    return warnings



def _sorted_ability_links(unit: models.Unit) -> list[models.UnitAbility]:
    links = list(getattr(unit, "abilities", []))
    links.sort(
        key=lambda link: (
            getattr(link, "position", 0),
            getattr(link, "id", 0) or 0,
        )
    )
    return links
