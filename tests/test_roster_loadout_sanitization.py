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
