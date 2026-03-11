from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import armies
from app.services import costs


def test_spell_weapon_cost_prefers_current_form_values_over_weapon_values() -> None:
    weapon = models.Weapon(name="Kostur", range='18"', attacks=1, ap=0, tags=None)
    form_values = {
        "name": "Kostur",
        "range": '18"',
        "attacks": "1",
        "ap": "3",
        "abilities": [],
        "notes": "",
    }

    preview_cost = armies._spell_weapon_cost(weapon, form_values)

    expected_raw_cost = costs.weapon_cost(
        models.Weapon(name="Kostur", range='18"', attacks=1, ap=3, tags=None),
        unit_quality=4,
    )
    expected_spell_cost = int(math.ceil(max(expected_raw_cost, 0.0) / 7.0))

    assert preview_cost == expected_spell_cost


def test_spell_weapon_cost_uses_weapon_cost_when_form_values_missing() -> None:
    weapon = models.Weapon(name="Kostur", range='18"', attacks=1, ap=2, tags=None)

    preview_cost = armies._spell_weapon_cost(weapon, None)
    _, _, spell_cost = armies._weapon_spell_details(weapon)

    assert preview_cost == spell_cost
