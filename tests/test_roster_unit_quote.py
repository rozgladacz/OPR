from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs


def _weapon(weapon_id: int, *, ap: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=weapon_id,
        range='18"',
        attacks=1,
        ap=ap,
        tags="",
        parent=None,
    )


def _unit() -> SimpleNamespace:
    base_weapon = _weapon(101)
    return SimpleNamespace(
        quality=4,
        defense=4,
        toughness=1,
        flags="Wojownik",
        army=None,
        abilities=[],
        weapon_links=[
            SimpleNamespace(
                weapon_id=101,
                weapon=base_weapon,
                is_default=True,
                default_count=1,
            )
        ],
        default_weapon=base_weapon,
        default_weapon_id=101,
    )


def test_calculate_roster_unit_quote_returns_contract_fields() -> None:
    quote = costs.calculate_roster_unit_quote(_unit(), loadout={}, count=3)

    assert quote["cost_engine_version"] == costs.COST_ENGINE_VERSION
    assert quote["selected_role"] in {"wojownik", "strzelec"}
    assert set(quote["components"]) == {"base", "weapon", "active", "aura", "passive"}
    assert quote["selected_total"] == max(quote["warrior_total"], quote["shooter_total"])


def test_calculate_roster_unit_quote_normalizes_loadout() -> None:
    raw_loadout = {
        "mode": "TOTAL",
        "weapons": {"101": 2, "999": 5, "bad": 3},
        "active": {"22": 1},
        "aura": {"31": 1},
        "passive": {"wojownik": 1, "unknown": 1},
    }

    quote = costs.calculate_roster_unit_quote(_unit(), loadout=raw_loadout, count=2)

    normalized = quote["loadout"]
    assert normalized["mode"] == "total"
    assert normalized["weapons"] == {"101": 2}
    assert normalized["active"] == {}
    assert normalized["aura"] == {}
    assert normalized["passive"] == {"wojownik": 1}


def test_calculate_roster_unit_quote_uses_selected_role_variant_components() -> None:
    quote = costs.calculate_roster_unit_quote(_unit(), loadout={}, count=1)

    assert quote["selected_total"] == quote["shooter_total"]
    assert quote["selected_role"] == "strzelec"

    base_traits = costs._strip_role_traits(costs.compute_passive_state(_unit(), quote["loadout"]).traits)
    shooter_traits = costs._with_role_trait(base_traits, "strzelec")
    expected_base = round(
        costs.base_model_cost(4, 4, 1, shooter_traits),
        2,
    )
    expected_weapon = round(
        costs.weapon_cost(_unit().default_weapon, 4, shooter_traits),
        2,
    )

    assert quote["components"]["base"] == expected_base
    assert quote["components"]["weapon"] == expected_weapon
    assert round(sum(quote["components"].values()), 2) == quote["shooter_total"]
