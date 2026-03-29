from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _legacy_section_total(
    unit: SimpleNamespace,
    normalized_loadout: dict[str, object],
    base_traits: list[str],
    selected_traits: list[str],
    model_count: int,
    *,
    section: str,
    ability: bool = False,
) -> float:
    data = normalized_loadout.get(section)
    if not isinstance(data, dict):
        return 0.0
    mode_total = normalized_loadout.get("mode") == "total"
    total = 0.0
    for raw_key, raw_count in data.items():
        key_str = str(raw_key).strip()
        if not key_str:
            continue
        base_id = key_str.split(":", 1)[0]
        try:
            item_id = int(base_id)
        except (TypeError, ValueError):
            continue
        per_model_count = max(int(raw_count), 0)
        if per_model_count <= 0:
            continue
        multiplier = 1 if mode_total else model_count
        if ability and any(costs.ability_identifier(trait) == "masywny" for trait in base_traits):
            multiplier = 1
        selected_count = per_model_count if mode_total else per_model_count * multiplier
        if section == "weapons":
            link = next(
                (
                    item
                    for item in getattr(unit, "weapon_links", []) or []
                    if getattr(item, "weapon_id", None) == item_id
                    and getattr(item, "weapon", None) is not None
                ),
                None,
            )
            weapon = getattr(link, "weapon", None)
            if weapon is None and getattr(unit, "default_weapon_id", None) == item_id:
                weapon = getattr(unit, "default_weapon", None)
            if weapon is None:
                continue
            total += costs.weapon_cost(weapon, unit.quality, selected_traits) * selected_count
        else:
            ability_link = next(
                (
                    item
                    for item in getattr(unit, "abilities", []) or []
                    if getattr(getattr(item, "ability", None), "id", None) == item_id
                ),
                None,
            )
            if ability_link is None:
                continue
            total += (
                costs.ability_cost(ability_link, selected_traits, toughness=unit.toughness)
                * selected_count
            )
    return round(total, 2)


def test_calculate_roster_unit_quote_preserves_totals_for_suffixed_loadout_keys() -> None:
    default_weapon = _weapon(101, ap=1)
    heavy_weapon = _weapon(102, ap=3)
    active_ability = SimpleNamespace(id=201, name="Scout", type="active", cost_hint=3, config_json=None)
    aura_ability = SimpleNamespace(id=202, name="Fear", type="aura", cost_hint=2, config_json=None)
    unit = SimpleNamespace(
        quality=4,
        defense=4,
        toughness=1,
        flags="Wojownik",
        army=None,
        abilities=[
            SimpleNamespace(ability=active_ability, params_json=None, unit=None),
            SimpleNamespace(ability=aura_ability, params_json=None, unit=None),
        ],
        weapon_links=[
            SimpleNamespace(weapon_id=101, weapon=default_weapon, is_default=True, default_count=1),
            SimpleNamespace(weapon_id=102, weapon=heavy_weapon, is_default=False, default_count=0),
        ],
        default_weapon=default_weapon,
        default_weapon_id=101,
    )
    loadout = {
        "mode": "per_model",
        "weapons": {"101": 1, "102:alt_profile": 2},
        "active": {"201:banner": 1},
        "aura": {"202:fearful": 1},
    }
    quote = costs.calculate_roster_unit_quote(unit, loadout=loadout, count=2)
    normalized_loadout = quote["loadout"]
    base_traits = costs._strip_role_traits(costs.compute_passive_state(unit, normalized_loadout).traits)
    selected_role = quote["selected_role"]
    selected_traits = costs._with_role_trait(base_traits, selected_role)
    model_count = 2

    expected_weapon = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        model_count,
        section="weapons",
    )
    expected_active = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        model_count,
        section="active",
        ability=True,
    )
    expected_aura = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        model_count,
        section="aura",
        ability=True,
    )

    assert quote["components"]["weapon"] == expected_weapon
    assert quote["components"]["active"] == expected_active
    assert quote["components"]["aura"] == expected_aura


@pytest.mark.parametrize("mode", ["per_model", "total"])
def test_calculate_roster_unit_quote_matches_legacy_section_totals_regression(mode: str) -> None:
    default_weapon = _weapon(101, ap=1)
    heavy_weapon = _weapon(102, ap=3)
    active_ability = SimpleNamespace(id=201, name="Scout", type="active", cost_hint=3, config_json=None)
    aura_ability = SimpleNamespace(id=202, name="Fear", type="aura", cost_hint=2, config_json=None)
    unit = SimpleNamespace(
        quality=4,
        defense=4,
        toughness=1,
        flags="Wojownik,Masywny",
        army=None,
        abilities=[
            SimpleNamespace(ability=active_ability, params_json=None, unit=None),
            SimpleNamespace(ability=aura_ability, params_json=None, unit=None),
        ],
        weapon_links=[
            SimpleNamespace(weapon_id=101, weapon=default_weapon, is_default=True, default_count=1),
            SimpleNamespace(weapon_id=102, weapon=heavy_weapon, is_default=False, default_count=0),
        ],
        default_weapon=default_weapon,
        default_weapon_id=101,
    )
    loadout = {
        "mode": mode,
        "weapons": {"101:base": 1, "102:alt": 2},
        "active": {"201:banner": 2},
        "aura": {"202:fearful": 1},
    }

    quote = costs.calculate_roster_unit_quote(unit, loadout=loadout, count=3)
    normalized_loadout = quote["loadout"]
    base_traits = costs._strip_role_traits(costs.compute_passive_state(unit, normalized_loadout).traits)
    selected_traits = costs._with_role_trait(base_traits, quote["selected_role"])

    expected_weapon = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        3,
        section="weapons",
    )
    expected_active = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        3,
        section="active",
        ability=True,
    )
    expected_aura = _legacy_section_total(
        unit,
        normalized_loadout,
        base_traits,
        selected_traits,
        3,
        section="aura",
        ability=True,
    )

    assert quote["components"]["weapon"] == expected_weapon
    assert quote["components"]["active"] == expected_active
    assert quote["components"]["aura"] == expected_aura


@pytest.mark.parametrize("count", [0, -1, -5])
def test_calculate_roster_unit_quote_rejects_non_positive_count(count: int) -> None:
    with pytest.raises(ValueError, match="count must be greater than 0"):
        costs.calculate_roster_unit_quote(_unit(), loadout={}, count=count)
