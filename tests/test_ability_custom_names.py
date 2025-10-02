import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import rosters


def _make_unit() -> models.Unit:
    unit = models.Unit(
        name="Test",
        quality=4,
        defense=3,
        toughness=4,
        army_id=1,
    )
    unit.abilities = []
    unit.weapon_links = []
    return unit


def test_sanitize_loadout_preserves_valid_custom_names():
    unit = _make_unit()
    payload = {
        "active": {"7": 2, "8": 0},
        "aura": {"9": 1},
        "active_labels": {"7": "Medyk", "8": "Unused"},
        "aura_labels": {"9": "Psyker"},
    }
    active_items = [{"ability_id": 7, "default_count": 0}]
    aura_items = [{"ability_id": 9, "default_count": 0}]

    sanitized = rosters._sanitize_loadout(
        unit,
        model_count=3,
        payload=payload,
        weapon_options=[],
        active_items=active_items,
        aura_items=aura_items,
        passive_items=[],
    )

    assert sanitized["active"].get("7") == 2
    assert sanitized["active_labels"] == {"7": "Medyk"}
    assert sanitized["aura_labels"] == {"9": "Psyker"}


def test_selected_ability_entries_include_custom_names():
    loadout = {
        "active": {"7": 1},
        "active_labels": {"7": "Medyk"},
    }
    ability_items = [{"ability_id": 7, "label": "Aura: Regeneracja", "description": ""}]

    selected = rosters._selected_ability_entries(loadout, ability_items, "active")

    assert selected and selected[0]["custom_name"] == "Medyk"


def test_ability_label_with_count_uses_custom_name():
    entry = {"label": "Aura: Regeneracja", "count": 1, "custom_name": "Medyk"}

    assert rosters._ability_label_with_count(entry) == "Medyk [Aura: Regeneracja]"

    entry_with_count = {"label": "Mag", "count": 2, "custom_name": "Psyker"}

    assert rosters._ability_label_with_count(entry_with_count) == "Psyker [Mag] ×2"
