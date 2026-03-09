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
