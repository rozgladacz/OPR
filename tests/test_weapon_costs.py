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
