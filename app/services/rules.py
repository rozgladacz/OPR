from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List

from .. import models
from ..data import abilities as ability_catalog
from . import ability_registry, costs, utils


@dataclass
class UnitSummary:
    """Light-weight snapshot of a roster entry used for soft validation."""

    name: str
    models: int
    total_cost: float
    active_count: int
    has_aura: bool
    hero_models: int


def _unit_is_hero(unit: models.Unit) -> bool:
    for link in getattr(unit, "abilities", []):
        ability = getattr(link, "ability", None)
        if not ability:
            continue
        slug = ability_registry.ability_slug(ability)
        if not slug and ability.name:
            slug = ability_catalog.slug_for_name(ability.name)
        if slug == "bohater":
            return True
    flags = utils.parse_flags(getattr(unit, "flags", None))
    for key in flags:
        slug = ability_catalog.slug_for_name(str(key)) or str(key).casefold()
        if slug == "bohater":
            return True
    return False


def _active_count(unit: models.Unit) -> int:
    return sum(
        1
        for link in getattr(unit, "abilities", [])
        if getattr(getattr(link, "ability", None), "type", "") == "active"
    )


def _has_aura(unit: models.Unit) -> bool:
    return any(
        getattr(getattr(link, "ability", None), "type", "").casefold() == "aura"
        for link in getattr(unit, "abilities", [])
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
        active_cnt = _active_count(unit)
        summary = UnitSummary(
            name=getattr(unit, "name", "Jednostka"),
            models=models_count,
            total_cost=total_cost,
            active_count=active_cnt,
            has_aura=_has_aura(unit),
            hero_models=models_count if _unit_is_hero(unit) else 0,
        )
        yield summary


def collect_roster_warnings(roster: models.Roster) -> List[str]:
    config = costs.default_ruleset_config()
    warnings_cfg = config.get("warnings", {}) if isinstance(config, dict) else {}

    max_models = int(warnings_cfg.get("max_models", 21) or 21)
    min_unit_cost = float(warnings_cfg.get("min_unit_cost", 50) or 50)
    max_share = float(warnings_cfg.get("max_share", 0.35) or 0.35)
    heroes_per_points = int(warnings_cfg.get("heroes_per_points", 500) or 500)

    total_cost = float(costs.roster_total(roster))
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
        if summary.active_count >= 1 and summary.has_aura:
            warnings.append(
                f"[AURA] Jednostka '{summary.name}' ma jednocześnie aurę i zdolność aktywną."
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
            if summary.total_cost < min_unit_cost:
                warnings.append(
                    f"[LIMIT] '{summary.name}' kosztuje {summary.total_cost:.0f} pkt (< {int(min_unit_cost)} pkt)."
                )

    if heroes_per_points > 0 and total_cost > 0:
        hero_models = sum(item.hero_models for item in summaries)
        allowed = max(1, math.floor(total_cost / heroes_per_points))
        if hero_models > allowed:
            warnings.append(
                f"[HERO] Bohaterów {hero_models}, standard: ≤ {allowed} (1/{heroes_per_points} pkt)."
            )

    return warnings

