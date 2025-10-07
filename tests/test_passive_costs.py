from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from app import models
from app.services import costs, utils as service_utils

if not hasattr(service_utils, "HIDDEN_TRAIT_SLUGS"):
    service_utils.HIDDEN_TRAIT_SLUGS = set()

from app.routers import rosters


def _make_unit_with_default_passive() -> models.Unit:
    ability = models.Ability(name="Nieustraszony", type="passive", description="")
    link = models.UnitAbility()
    link.ability = ability
    unit = models.Unit(
        name="Veterans",
        quality=4,
        defense=3,
        toughness=6,
        flags="Nieustraszony",
        army_id=1,
    )
    unit.abilities = [link]
    unit.weapon_links = []
    unit.default_weapon = None
    unit.default_weapon_id = None
    return unit


def test_disabling_default_passive_reduces_cost() -> None:
    unit = _make_unit_with_default_passive()
    roster_unit = models.RosterUnit(unit=unit, count=1)

    totals_default = costs.roster_unit_role_totals(roster_unit)
    disabled_payload = {"passive": {"Nieustraszony": 0}}
    totals_disabled = costs.roster_unit_role_totals(roster_unit, disabled_payload)

    assert totals_disabled["wojownik"] < totals_default["wojownik"]
    assert totals_disabled["strzelec"] <= totals_default["strzelec"]


def test_base_cost_per_model_respects_classification() -> None:
    unit = models.Unit(
        name="Infantry",
        quality=4,
        defense=4,
        toughness=6,
        flags=None,
        army_id=1,
    )
    unit.abilities = []
    unit.weapon_links = []
    unit.default_weapon = None
    unit.default_weapon_id = None

    passive_state = costs.compute_passive_state(unit)
    base_traits = [
        trait
        for trait in passive_state.traits
        if costs.ability_identifier(trait) not in costs.ROLE_SLUGS
    ]
    expected_warrior = costs.base_model_cost(
        unit.quality,
        unit.defense,
        unit.toughness,
        base_traits + ["wojownik"],
    )
    warrior_base = rosters._base_cost_per_model(unit, {"slug": "wojownik"})
    assert warrior_base == round(expected_warrior, 2)

    expected_shooter = costs.base_model_cost(
        unit.quality,
        unit.defense,
        unit.toughness,
        base_traits + ["strzelec"],
    )
    shooter_base = rosters._base_cost_per_model(unit, {"slug": "strzelec"})
    assert shooter_base == round(expected_shooter, 2)


def test_delikatny_cost_matches_defense_row_difference() -> None:
    unit = models.Unit(
        name="Fragile Troops",
        quality=4,
        defense=3,
        toughness=6,
        flags="Delikatny",
        army_id=1,
    )
    unit.abilities = []
    unit.weapon_links = []
    unit.default_weapon = None
    unit.default_weapon_id = None

    entries = rosters._passive_entries(unit)
    delikatny_entry = next(
        entry for entry in entries if costs.ability_identifier(entry.get("slug")) == "delikatny"
    )

    traits_with = costs.flags_to_ability_list({"Delikatny": True})
    traits_without = [
        trait
        for trait in traits_with
        if costs.ability_identifier(trait) != "delikatny"
    ]
    cost_with = costs.base_model_cost(
        unit.quality,
        unit.defense,
        unit.toughness,
        traits_with,
    )
    cost_without = costs.base_model_cost(
        unit.quality,
        unit.defense,
        unit.toughness,
        traits_without,
    )

    expected = cost_with - cost_without
    assert delikatny_entry["cost"] == pytest.approx(expected, rel=1e-6)


def test_defense_abilities_stack_additively() -> None:
    base_kwargs = dict(quality=4, defense=4, toughness=6)
    traits_with_both = ["niewrazliwy", "regeneracja"]
    cost_with_both = costs.base_model_cost(
        base_kwargs["quality"],
        base_kwargs["defense"],
        base_kwargs["toughness"],
        traits_with_both,
    )
    cost_without_niewrazliwy = costs.base_model_cost(
        base_kwargs["quality"],
        base_kwargs["defense"],
        base_kwargs["toughness"],
        ["regeneracja"],
    )
    cost_without_regeneracja = costs.base_model_cost(
        base_kwargs["quality"],
        base_kwargs["defense"],
        base_kwargs["toughness"],
        ["niewrazliwy"],
    )
    cost_without_both = costs.base_model_cost(
        base_kwargs["quality"],
        base_kwargs["defense"],
        base_kwargs["toughness"],
        [],
    )

    diff_both = cost_with_both - cost_without_both
    diff_niewrazliwy = cost_with_both - cost_without_niewrazliwy
    diff_regeneracja = cost_with_both - cost_without_regeneracja

    assert diff_both == pytest.approx(diff_niewrazliwy + diff_regeneracja, rel=1e-6)


def test_szpica_defense_modifier_matches_table() -> None:
    quality = 4
    defense = 4
    toughness = 6
    base_cost = costs.base_model_cost(quality, defense, toughness, [])
    szpica_cost = costs.base_model_cost(quality, defense, toughness, ["szpica"])

    morale = costs.morale_modifier(quality)
    toughness_value = costs.toughness_modifier(toughness)
    delta = costs.DEFENSE_ABILITY_MODIFIERS["szpica"][defense]
    expected = costs.BASE_COST_FACTOR * morale * toughness_value * delta

    assert szpica_cost - base_cost == pytest.approx(expected, rel=1e-6)


def test_szpica_increases_weapon_hit_chance() -> None:
    weapon = models.Weapon(attacks=1.0, ap=0, range="Melee", armory_id=1)

    cost_without = costs.weapon_cost(weapon, unit_quality=4, unit_flags=[])
    cost_with = costs.weapon_cost(weapon, unit_quality=4, unit_flags=["Szpica"])

    range_mod = costs.range_multiplier(0)
    ap_mod = costs.lookup_with_nearest(costs.AP_BASE, 0)
    expected_delta = round(2.0 * range_mod * ap_mod * 0.5, 2)

    assert cost_with - cost_without == pytest.approx(expected_delta, rel=1e-6)
def test_instynkt_cost_scaling_with_toughness() -> None:
    assert costs.passive_cost("instynkt", 5) == pytest.approx(-5)


def test_instynkt_aura_and_order_costs() -> None:
    assert costs.passive_cost("instynkt", 8, True) == pytest.approx(8)
    assert costs.passive_cost("instynkt", 10, True) == pytest.approx(10)
