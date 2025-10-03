from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import rosters


def _make_unit() -> SimpleNamespace:
    return SimpleNamespace(
        abilities=[],
        weapon_links=[],
        default_weapon_loadout=[],
        default_weapon_id=None,
        name="Test",  # pragma: nocover - metadata only
        flags="",
        quality=4,
        defense=3,
        toughness=4,
    )


def _make_aura_entry(ability_id: int, value: str, label: str) -> dict:
    return {
        "ability_id": ability_id,
        "label": label,
        "description": "",
        "cost": 5.0,
        "is_default": False,
        "default_count": 0,
        "custom_name": None,
        "value": value,
        "loadout_key": rosters._ability_loadout_key(ability_id, value),
    }


def test_sanitize_loadout_preserves_active_and_aura_counts() -> None:
    unit = _make_unit()
    payload = {
        "weapons": {},
        "active": {"5": 3},
        "aura": {"7": 1},
        "passive": {},
        "active_labels": {"5": "Medyk"},
        "aura_labels": {"7": "Osłona"},
    }

    result = rosters._sanitize_loadout(
        unit,
        model_count=5,
        payload=payload,
        weapon_options=[],
        active_items=[],
        aura_items=[],
        passive_items=[],
    )

    assert result["active"]["5"] == 3
    assert result["aura"]["7"] == 1
    assert result["active_labels"] == {"5": "Medyk"}
    assert result["aura_labels"] == {"7": "Osłona"}


def test_aura_variants_use_distinct_keys() -> None:
    unit = _make_unit()
    banner = _make_aura_entry(50, "banner", "Sztandar")
    medic = _make_aura_entry(50, "medic", "Medyk")

    payload = rosters._default_loadout_payload(
        unit,
        weapon_options=[],
        active_items=[],
        aura_items=[banner, medic],
        passive_items=[],
    )

    assert set(payload["aura"].keys()) == {
        rosters._ability_loadout_key(50, "banner"),
        rosters._ability_loadout_key(50, "medic"),
    }


def test_aura_variant_counts_remain_independent() -> None:
    unit = _make_unit()
    banner = _make_aura_entry(50, "banner", "Sztandar")
    medic = _make_aura_entry(50, "medic", "Medyk")
    banner_key = banner["loadout_key"]
    medic_key = medic["loadout_key"]

    payload = {
        "weapons": {},
        "active": {},
        "aura": {banner_key: 3, medic_key: 1},
        "passive": {},
        "aura_labels": {banner_key: "Sztandar", medic_key: "Medyk"},
        "active_labels": {},
    }

    sanitized = rosters._sanitize_loadout(
        unit,
        model_count=5,
        payload=payload,
        weapon_options=[],
        active_items=[],
        aura_items=[banner, medic],
        passive_items=[],
    )

    assert sanitized["aura"][banner_key] == 3
    assert sanitized["aura"][medic_key] == 1

    sanitized["aura"][banner_key] = 2

    refreshed = rosters._sanitize_loadout(
        unit,
        model_count=5,
        payload=sanitized,
        weapon_options=[],
        active_items=[],
        aura_items=[banner, medic],
        passive_items=[],
    )

    assert refreshed["aura"][banner_key] == 2
    assert refreshed["aura"][medic_key] == 1
    assert refreshed["aura_labels"][banner_key] == "Sztandar"
    assert refreshed["aura_labels"][medic_key] == "Medyk"
