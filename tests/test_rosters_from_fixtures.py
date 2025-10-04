from __future__ import annotations

import glob
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.data import abilities as ability_catalog
from app.services import costs
from app.services.rules import collect_roster_warnings


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rosters"
_WEAPON_ID_SEQ = itertools.count(1)


TEMPLATE_LIBRARY: dict[str, dict[str, Any]] = {
    "Taktyczni": {
        "quality": 4,
        "defense": 2,
        "toughness": 6,
        "flags": "Nieustraszony",
        "weapon": {"name": "Bolter", "range": 12, "attacks": 2, "ap": 0, "traits": []},
        "base_models": 1,
        "abilities": [],
    },
    "Weterani": {
        "quality": 2,
        "defense": 3,
        "toughness": 6,
        "flags": "Regeneracja",
        "weapon": {
            "name": "Plazma",
            "range": 36,
            "attacks": 5,
            "ap": 2,
            "traits": ["Namierzanie", "Ciężki"],
        },
        "base_models": 4,
        "abilities": ["Bohater"],
    },
}


def _load_fixtures() -> Iterable[tuple[str, dict[str, Any]]]:
    for path in sorted(glob.glob(str(FIXTURE_DIR / "*.yml")) + glob.glob(str(FIXTURE_DIR / "*.yaml")) + glob.glob(str(FIXTURE_DIR / "*.json"))):
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) if path.endswith((".yml", ".yaml")) else json.load(handle)
        yield os.path.basename(path), data


def _ability_type(name: str) -> str:
    slug = ability_catalog.slug_for_name(name)
    definition = ability_catalog.find_definition(slug) if slug else None
    return definition.type if definition else "passive"


def _build_unit(
    template_name: str, overrides: dict[str, Any] | None
) -> tuple[models.Unit, int, dict[str, Any]]:
    if template_name not in TEMPLATE_LIBRARY:
        raise KeyError(f"Brak definicji szablonu jednostki: {template_name}")
    template = TEMPLATE_LIBRARY[template_name]
    overrides = overrides or {}
    unit = models.Unit(
        name=template_name,
        quality=template["quality"],
        defense=template["defense"],
        toughness=template["toughness"],
        flags=template.get("flags"),
        army_id=1,
    )

    ability_names: list[str] = []
    ability_names.extend(template.get("abilities", []))
    existing_slugs: set[str] = set()
    for source in (template.get("flags"),):
        if not source:
            continue
        for token in str(source).split(","):
            slug = ability_catalog.slug_for_name(token.strip())
            if slug:
                existing_slugs.add(slug)
    for name in ability_names:
        slug = ability_catalog.slug_for_name(name)
        if slug:
            existing_slugs.add(slug)
    for name in overrides.get("abilities", []) or []:
        slug = ability_catalog.slug_for_name(name)
        if slug and slug in existing_slugs:
            continue
        if name not in ability_names:
            ability_names.append(name)
            if slug:
                existing_slugs.add(slug)
    unit.abilities = []
    for name in ability_names:
        ability = models.Ability(name=name, type=_ability_type(name), description="")
        link = models.UnitAbility()
        link.ability = ability
        unit.abilities.append(link)

    def _make_weapon(payload: dict[str, Any]) -> models.Weapon:
        data = dict(payload or {})
        range_value = data.get("range")
        if isinstance(range_value, (int, float)):
            range_text = f"{int(range_value)}\""
        else:
            range_text = range_value or None
        traits = data.get("traits", []) or []
        weapon = models.Weapon(
            name=data.get("name"),
            range=range_text,
            attacks=data.get("attacks"),
            ap=data.get("ap"),
            tags=",".join(traits) if traits else None,
            armory_id=1,
        )
        weapon.id = int(data.get("id") or next(_WEAPON_ID_SEQ))
        return weapon

    weapon_payload = dict(template.get("weapon", {}))
    range_value = weapon_payload.get("range")
    if isinstance(range_value, (int, float)):
        range_text = f"{int(range_value)}\""
    else:
        range_text = range_value or None
    traits = weapon_payload.get("traits", []) or []
    weapon = _make_weapon(weapon_payload)
    unit.default_weapon = weapon
    unit.default_weapon_id = weapon.id
    unit.weapon_links = []

    override_entries: list[dict[str, Any]] = []
    raw_override_weapons = overrides.get("weapons")
    if isinstance(raw_override_weapons, dict):
        override_iterable = [raw_override_weapons]
    elif isinstance(raw_override_weapons, list):
        override_iterable = [entry for entry in raw_override_weapons if isinstance(entry, dict)]
    else:
        override_iterable = []
    for payload in override_iterable:
        custom_weapon = _make_weapon(payload)
        link = models.UnitWeapon()
        link.weapon = custom_weapon
        link.weapon_id = custom_weapon.id
        link.is_default = False
        link.default_count = 0
        unit.weapon_links.append(link)
        range_value = payload.get("range")
        try:
            numeric_range = int(float(range_value))
        except (TypeError, ValueError):
            numeric_range = None
        override_entries.append(
            {
                "id": custom_weapon.id,
                "is_melee": numeric_range == 0,
            }
        )

    context = {"override_weapons": override_entries}
    return unit, int(template.get("base_models", 1)), context


def _build_roster(roster_payload: dict[str, Any]) -> models.Roster:
    roster = models.Roster(
        name=roster_payload.get("name", "Testowa rozpiska"),
        army_id=1,
        points_limit=roster_payload.get("limit"),
        owner_id=None,
    )
    roster.roster_units = []
    for unit_payload in roster_payload.get("units", []):
        unit, base_models, context = _build_unit(
            unit_payload["template_unit"], unit_payload.get("overrides")
        )
        roster_unit = models.RosterUnit(
            unit=unit,
            count=int(unit_payload.get("models", 1)),
        )
        total_models = max(base_models * roster_unit.count, 0)
        setattr(roster_unit, "models", total_models)
        override_payload = context.get("override_weapons") if context else None
        if override_payload:
            melee_weapons = [entry["id"] for entry in override_payload if entry.get("is_melee")]
        else:
            melee_weapons = []
        if melee_weapons:
            loadout = {"mode": "per_model", "weapons": {}}
            if unit.default_weapon_id is not None:
                loadout["weapons"][str(unit.default_weapon_id)] = 0
            for weapon_id in melee_weapons:
                loadout["weapons"][str(weapon_id)] = 1
            roster_unit.extra_weapons_json = json.dumps(loadout, ensure_ascii=False)
        roster.roster_units.append(roster_unit)
    costs.update_cached_costs(roster.roster_units)
    for roster_unit in roster.roster_units:
        roster_unit.total_cost = roster_unit.cached_cost
    return roster


@pytest.mark.parametrize("fixture_name, payload", list(_load_fixtures()))
def test_rosters_from_fixtures(fixture_name: str, payload: dict[str, Any]) -> None:
    assert "rosters" in payload, f"Brak sekcji 'rosters' w {fixture_name}"

    for roster_payload in payload["rosters"]:
        roster = _build_roster(roster_payload)
        total = costs.roster_total(roster)
        expected_total = roster_payload.get("expected_total")
        if expected_total is not None:
            assert total == pytest.approx(float(expected_total), abs=1.5)

        warnings = collect_roster_warnings(roster)
        for needle in roster_payload.get("expected_warnings_contains", []) or []:
            assert any(needle in warning for warning in warnings), (
                f"Ostrzeżenie '{needle}' nie występuje w rozpisce '{roster.name}'"
            )

