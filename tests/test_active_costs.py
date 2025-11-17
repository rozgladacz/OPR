from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.data import abilities as ability_catalog
from app.services import costs


def test_latanie_cost_is_20():
    assert costs.ability_cost_from_name("Łatanie") == 20.0


def test_mobilizacja_cost_is_30():
    assert costs.ability_cost_from_name("Mobilizacja") == 30.0


def test_ability_identifier_ignores_diacritics():
    assert costs.ability_identifier("Łatanie") == "latanie"
    assert costs.normalize_name("Żółć") == "zolc"


def test_catalog_slug_lookup_handles_diacritics():
    assert ability_catalog.slug_for_name("Łatanie") == "latanie"
