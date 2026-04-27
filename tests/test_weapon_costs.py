import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs


def _weapon(
    range_value: str,
    attacks: float = 1.0,
    ap: int = 0,
    tags: str | None = None,
    cached_cost: float | None = None,
):
    return SimpleNamespace(
        effective_range=range_value,
        effective_attacks=attacks,
        effective_ap=ap,
        effective_tags=tags,
        effective_cached_cost=cached_cost,
    )


def test_warrior_reduces_ranged_weapon_cost():
    weapon = _weapon("24\"")
    base_cost = costs.weapon_cost(weapon, unit_quality=4, unit_flags=[])
    warrior_cost = costs.weapon_cost(weapon, unit_quality=4, unit_flags=["Wojownik"])

    assert warrior_cost < base_cost
    assert warrior_cost > 0


def test_shooter_reduces_melee_weapon_cost():
    weapon = _weapon("Melee")
    base_cost = costs.weapon_cost(weapon, unit_quality=4, unit_flags=[])
    shooter_cost = costs.weapon_cost(weapon, unit_quality=4, unit_flags=["Strzelec"])

    assert shooter_cost < base_cost
    assert shooter_cost > 0


def test_weapon_cost_uses_cached_value_for_default_queries(monkeypatch):
    weapon = _weapon("Melee", cached_cost=12.5)
    recorded_calls: list[tuple] = []

    def fake_weapon_cost(*args, **kwargs):
        recorded_calls.append((args, kwargs))
        return 99.0

    monkeypatch.setattr(costs, "_weapon_cost", fake_weapon_cost)

    assert costs.weapon_cost(weapon, unit_quality=4, unit_flags=[]) == pytest.approx(12.5)
    assert recorded_calls == []


def test_weapon_cost_falls_back_when_modifiers_present(monkeypatch):
    weapon = _weapon("Melee", cached_cost=12.5)
    recorded_calls: list[tuple] = []

    def fake_weapon_cost(*args, **kwargs):
        recorded_calls.append((args, kwargs))
        return 7.0

    monkeypatch.setattr(costs, "_weapon_cost", fake_weapon_cost)

    result = costs.weapon_cost(weapon, unit_quality=3, unit_flags=[])
    assert recorded_calls  # quality mismatch triggers recomputation
    assert result == pytest.approx(7.0)

    recorded_calls.clear()
    result = costs.weapon_cost(weapon, unit_quality=4, unit_flags=["Wojownik"])
    assert recorded_calls  # traits present trigger recomputation
    assert result == pytest.approx(7.0)


def test_artillery_increases_ranged_weapon_cost():
    base_weapon = _weapon("24\"")
    artillery_weapon = _weapon("24\"", tags="Artyleria")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=4, unit_flags=[])
    artillery_cost = costs.weapon_cost(artillery_weapon, unit_quality=4, unit_flags=[])

    assert artillery_cost > base_cost


def test_unwieldy_reduces_ranged_weapon_cost():
    base_weapon = _weapon("24\"")
    unwieldy_weapon = _weapon("24\"", tags="Nieporęczny")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=4, unit_flags=[])
    unwieldy_cost = costs.weapon_cost(unwieldy_weapon, unit_quality=4, unit_flags=[])

    assert unwieldy_cost < base_cost
    assert unwieldy_cost > 0


def test_podwojny_increases_weapon_cost():
    base_weapon = _weapon("24\"")
    double_weapon = _weapon("24\"", tags="Podwójny")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=4, unit_flags=[])
    double_cost = costs.weapon_cost(double_weapon, unit_quality=4, unit_flags=[])

    assert double_cost > base_cost


@pytest.mark.parametrize("quality", [2, 3, 4, 5, 6])
def test_finezja_uses_quality_scaled_hit_chance_bonus(quality: int) -> None:
    base_weapon = _weapon('24"', attacks=2, ap=1)
    finezja_weapon = _weapon('24"', attacks=2, ap=1, tags="Finezja")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=quality, unit_flags=[])
    finezja_cost = costs.weapon_cost(finezja_weapon, unit_quality=quality, unit_flags=[])

    range_mod = costs.lookup_with_nearest(costs.RANGE_TABLE, 24)
    ap_mod = costs.lookup_with_nearest(costs.AP_BASE, 1)
    finezja_bonus = ((7 - quality) * (6 - quality) ** 2) / 50.0
    expected_delta = 2 * 2.0 * range_mod * finezja_bonus * ap_mod

    assert finezja_cost - base_cost == pytest.approx(expected_delta, abs=0.02)


@pytest.mark.parametrize("ap,expected_bonus", [
    (-1, 0.0), (0, 0.01), (1, 0.02), (2, 0.1), (3, 0.2), (4, 0.3), (5, 0.4),
])
def test_brutalny_uses_ap_based_cost(ap: int, expected_bonus: float) -> None:
    base_weapon = _weapon('24"', attacks=2, ap=ap)
    brutal_weapon = _weapon('24"', attacks=2, ap=ap, tags="Brutalny")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=4, unit_flags=[])
    brutal_cost = costs.weapon_cost(brutal_weapon, unit_quality=4, unit_flags=[])

    range_mod = costs.lookup_with_nearest(costs.RANGE_TABLE, 24)
    chance = max(7.0 - 0.6 - 4, 0.9)
    expected_delta = round(2 * 2.0 * range_mod * chance * expected_bonus, 2)

    assert brutal_cost - base_cost == pytest.approx(expected_delta, abs=0.02)


def test_overcharge_applied_once_for_non_assault():
    base_weapon = _weapon("24\"", ap=4, tags="Deadly(2), Blast(3)")
    overcharge_weapon = _weapon("24\"", ap=4, tags="Deadly(2), Blast(3), Overcharge")

    base_cost = costs.weapon_cost(base_weapon, unit_quality=4, unit_flags=[])
    overcharge_cost = costs.weapon_cost(overcharge_weapon, unit_quality=4, unit_flags=[])

    assert overcharge_cost == pytest.approx(base_cost * 1.05, rel=1e-3, abs=0.02)


def test_overcharge_applies_once_per_assault_component():
    ranged_base = costs._weapon_cost(
        4,
        12,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )
    melee_base = costs._weapon_cost(
        4,
        0,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )

    expected = 1.05 * ranged_base + melee_base
    assault_overcharge = _weapon("12\"", ap=1, tags="Assault, Overcharge")
    total_cost = costs.weapon_cost(assault_overcharge, unit_quality=4, unit_flags=[])

    assert total_cost == pytest.approx(expected, rel=1e-3, abs=0.02)
def test_ambush_assault_reduces_only_ranged_component() -> None:
    ranged_component = costs._weapon_cost(
        4,
        12,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )
    melee_component = costs._weapon_cost(
        4,
        0,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )
    expected = ranged_component * 0.6 + melee_component

    assault_weapon = _weapon("12\"", ap=1, tags="Assault")
    ambush_cost = costs.weapon_cost(
        assault_weapon,
        unit_quality=4,
        unit_flags=["Zasadzka"],
    )

    assert ambush_cost == pytest.approx(expected, rel=1e-3, abs=0.02)


def test_reserve_assault_reduces_both_components() -> None:
    ranged_component = costs._weapon_cost(
        4,
        12,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )
    melee_component = costs._weapon_cost(
        4,
        0,
        1,
        1,
        ["Assault"],
        [],
        allow_assault_extra=False,
    )
    expected = (ranged_component + melee_component) * 0.6

    assault_weapon = _weapon("12\"", ap=1, tags="Assault")
    reserve_cost = costs.weapon_cost(
        assault_weapon,
        unit_quality=4,
        unit_flags=["Rezerwa"],
    )

    assert reserve_cost == pytest.approx(expected, rel=1e-3, abs=0.02)


def test_porazenie_increases_only_melee_weapon_cost() -> None:
    melee_base = _weapon("Melee", attacks=2, ap=1)
    melee_porazenie = _weapon("Melee", attacks=2, ap=1, tags="Porażenie")
    ranged_base = _weapon('24"', attacks=2, ap=1)
    ranged_porazenie = _weapon('24"', attacks=2, ap=1, tags="Porażenie")

    melee_base_cost = costs.weapon_cost(melee_base, unit_quality=4, unit_flags=[])
    melee_porazenie_cost = costs.weapon_cost(melee_porazenie, unit_quality=4, unit_flags=[])
    ranged_base_cost = costs.weapon_cost(ranged_base, unit_quality=4, unit_flags=[])
    ranged_porazenie_cost = costs.weapon_cost(ranged_porazenie, unit_quality=4, unit_flags=[])

    assert melee_porazenie_cost == pytest.approx(melee_base_cost * 1.1, rel=1e-3, abs=0.02)
    assert ranged_porazenie_cost == pytest.approx(ranged_base_cost, rel=1e-3, abs=0.02)


def test_weapon_cost_components_total_matches_legacy_total_without_classification() -> None:
    weapon = _weapon('24"', attacks=2, ap=1, tags="Assault, Deadly(2)")
    legacy_total = costs.weapon_cost(weapon, unit_quality=4, unit_flags=[])
    components = costs.weapon_cost_components(weapon, unit_quality=4, unit_flags=[])

    assert components["melee"] > 0
    assert components["ranged"] > 0
    assert components["total"] == pytest.approx(legacy_total, abs=0.01)
    assert round(components["melee"] + components["ranged"], 2) == pytest.approx(
        legacy_total,
        abs=0.01,
    )
