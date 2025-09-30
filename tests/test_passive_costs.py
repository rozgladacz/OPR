from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import rosters
from app.services import costs


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
