from types import SimpleNamespace

from app.services import costs


def _weapon(range_value: str, attacks: float = 1.0, ap: int = 0, tags: str | None = None):
    return SimpleNamespace(
        effective_range=range_value,
        effective_attacks=attacks,
        effective_ap=ap,
        effective_tags=tags,
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
