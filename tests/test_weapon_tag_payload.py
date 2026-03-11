from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import armories, armies


def test_weapon_tags_payload_does_not_include_bez_oslon_slug():
    payload = armories._weapon_tags_payload("No Cover, Bez osłon, Namierzanie")

    slugs = {item["slug"] for item in payload}
    assert "bez_oslon" not in slugs


def test_spell_weapon_tags_payload_does_not_include_bez_oslon_slug():
    payload = armies._spell_weapon_tags_payload("No Cover, Bez osłon, Namierzanie")

    slugs = {item["slug"] for item in payload}
    assert "bez_oslon" not in slugs


def test_spell_weapon_tags_payload_filters_forbidden_spell_traits():
    payload = armies._spell_weapon_tags_payload(
        "Impet, Zużywalny, Niezawodny, Szturmowa, Podwójny, Nieporęczny, Przełamanie, Unik, Podkręcenie, Namierzanie"
    )

    slugs = {item["slug"] for item in payload}
    assert "namierzanie" in slugs
    assert "impet" not in slugs
    assert "zuzywalny" not in slugs
    assert "niezawodny" not in slugs
    assert "szturmowa" not in slugs
    assert "rozrywajacy" not in slugs
    assert "nieporeczny" not in slugs
    assert "burzaca" not in slugs
    assert "unik" not in slugs
    assert "podkrecenie" not in slugs


def test_spell_weapon_abilities_always_include_lock_on():
    filtered = armies._ensure_spell_weapon_has_lock_on([])

    slugs = {item["slug"] for item in filtered}
    assert "namierzanie" in slugs
