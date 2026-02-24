from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from app.data import abilities as ability_catalog


def test_aura_description_without_12_range_uses_bez_x_template() -> None:
    aura = ability_catalog.find_definition("aura")
    assert aura is not None

    description = ability_catalog.description_with_value(aura, "regeneracja")

    assert description.startswith("Bez X: Modele w twoim oddziale otrzymują zdolność:")
    regeneracja = ability_catalog.find_definition("regeneracja")
    assert regeneracja is not None
    assert regeneracja.description in description


def test_aura_description_with_12_range_uses_aura_template() -> None:
    aura = ability_catalog.find_definition("aura")
    assert aura is not None

    description = ability_catalog.description_with_value(aura, "regeneracja|12\"")

    assert description.startswith('Aura(12"): Modele w oddziałach w zasięgu 12" otrzymują zdolność:')
    regeneracja = ability_catalog.find_definition("regeneracja")
    assert regeneracja is not None
    assert regeneracja.description in description
