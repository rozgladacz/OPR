"""Prosty kalkulator kosztów jednostek i broni.

Docelowo tabele modyfikatorów powinny zostać rozszerzone zgodnie z zasadami OPR.
"""
from __future__ import annotations

from typing import Iterable

from .. import models
from .utils import parse_flags

QUALITY_COSTS = {2: 45, 3: 35, 4: 25, 5: 15, 6: 10}
DEFENSE_MODIFIERS = {2: 15, 3: 10, 4: 0, 5: -5, 6: -10}
TOUGHNESS_POINT = 5
FLAG_MODIFIERS = {
    "flying": 10,
    "good_shot": 5,
    "bad_shot": -5,
    "fear": 8,
}

WEAPON_TAG_BONUS = {
    "Ranged": 5,
    "Melee": 0,
    "Blast": 10,
    "Sniper": 6,
    "Heavy": 4,
}


def base_model_cost(quality: int, defense: int, toughness: int, flags: dict | None) -> float:
    """Zwraca koszt bazowy modelu na podstawie statystyk."""
    cost = QUALITY_COSTS.get(quality, 20) + DEFENSE_MODIFIERS.get(defense, 0)
    cost += max(toughness, 1) * TOUGHNESS_POINT

    for key, value in (flags or {}).items():
        modifier = FLAG_MODIFIERS.get(key, 0)
        if isinstance(value, (int, float)):
            modifier *= float(value)
        cost += modifier

    return max(cost, 5)


def weapon_cost(weapon: models.Weapon, unit_flags: dict | None = None) -> float:
    """Szacuje koszt broni biorąc pod uwagę liczbę ataków i AP."""
    attacks = weapon.attacks or 1
    ap_bonus = weapon.ap * 2
    tags = (weapon.tags or "").split(",")
    tag_bonus = sum(WEAPON_TAG_BONUS.get(tag.strip(), 0) for tag in tags if tag.strip())

    base = attacks * 6 + ap_bonus + tag_bonus
    if unit_flags and unit_flags.get("good_shot") and "Ranged" in [t.strip() for t in tags]:
        base += 4
    if unit_flags and unit_flags.get("bad_shot") and "Ranged" in [t.strip() for t in tags]:
        base -= 4
    return max(base, 2)


def ability_cost(ability_link: models.UnitAbility) -> float:
    if ability_link.ability and ability_link.ability.cost_hint is not None:
        return float(ability_link.ability.cost_hint)
    return 0.0


def unit_total_cost(unit: models.Unit) -> float:
    flags = parse_flags(unit.flags)
    cost = base_model_cost(unit.quality, unit.defense, unit.toughness, flags)
    if unit.default_weapon:
        cost += weapon_cost(unit.default_weapon, flags)
    cost += sum(ability_cost(link) for link in unit.abilities)
    return round(cost, 2)


def roster_unit_cost(roster_unit: models.RosterUnit) -> float:
    unit_cost = unit_total_cost(roster_unit.unit)
    flags = parse_flags(roster_unit.unit.flags)

    weapon = roster_unit.selected_weapon or roster_unit.unit.default_weapon
    if weapon:
        unit_cost = base_model_cost(
            roster_unit.unit.quality,
            roster_unit.unit.defense,
            roster_unit.unit.toughness,
            flags,
        )
        unit_cost += weapon_cost(weapon, flags)
        unit_cost += sum(ability_cost(link) for link in roster_unit.unit.abilities)

    total = unit_cost * max(roster_unit.count, 1)
    if roster_unit.extra_weapons_json:
        total += 5
    return round(total, 2)


def roster_total(roster: models.Roster) -> float:
    return round(sum(roster_unit_cost(ru) for ru in roster.roster_units), 2)


def update_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for ru in roster_units:
        ru.cached_cost = roster_unit_cost(ru)
