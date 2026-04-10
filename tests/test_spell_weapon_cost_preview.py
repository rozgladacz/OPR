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
def test_spell_weapon_cost_uses_weapon_cost_when_form_values_missing() -> None:
    weapon = models.Weapon(name="Kostur", range='18"', attacks=1, ap=2, tags=None)

    preview_cost = armies._spell_weapon_cost(weapon, None)
    _, _, spell_cost = armies._weapon_spell_details(weapon)

    assert preview_cost == spell_cost
