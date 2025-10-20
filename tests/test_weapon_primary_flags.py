import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import armies


class DummyDB:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, model, key):
        return self._mapping.get(key)

    def execute(self, _):  # pragma: no cover - helper for parsing tests
        class DummyResult:
            def __init__(self, values):
                self._values = values

            def scalars(self):
                return iter(self._values)

        return DummyResult(list(self._mapping.values()))


class DummySession:
    def __getattr__(self, name):  # pragma: no cover - unused hooks
        raise AttributeError(name)


def _make_weapon(
    weapon_id: int,
    *,
    armory_id: int = 1,
    range_value: float | int | None = None,
    name: str | None = None,
):
    return SimpleNamespace(
        id=weapon_id,
        armory_id=armory_id,
        effective_range=range_value,
        range=None,
        range_category=None,
        type="melee" if not range_value else "ranged",
        effective_name=name or f"Weapon {weapon_id}",
        effective_attacks=1,
        effective_ap=0,
        effective_tags="",
    )


def test_parse_weapon_payload_preserves_multiple_primary_flags():
    armory = SimpleNamespace(id=7)
    weapons = {
        1: _make_weapon(1, armory_id=7, range_value=0),
        2: _make_weapon(2, armory_id=7, range_value=0),
    }
    db = DummyDB(weapons)
    payload = json.dumps(
        [
            {"weapon_id": 1, "count": 1, "is_primary": True},
            {"weapon_id": 2, "count": 1, "is_primary": True},
        ]
    )

    entries = armies._parse_weapon_payload(db, armory, payload)

    assert len(entries) == 2
    assert all(is_primary for _, is_primary, _ in entries)


def test_parse_weapon_payload_ignores_primary_when_count_zero():
    armory = SimpleNamespace(id=3)
    weapons = {1: _make_weapon(1, armory_id=3, range_value=0)}
    db = DummyDB(weapons)
    payload = json.dumps([{"weapon_id": 1, "count": 0, "is_primary": True}])

    entries = armies._parse_weapon_payload(db, armory, payload)

    assert entries == [(weapons[1], False, 0)]


def test_apply_unit_form_data_sets_primary_flags_on_links():
    armory = models.Armory(name="Test Armory")
    ruleset = models.RuleSet(name="Test Ruleset")
    army = models.Army(name="Test Army", ruleset=ruleset, armory=armory)
    unit = models.Unit(
        name="Base", quality=4, defense=3, toughness=4, army=army, flags=""
    )
    weapon_a = models.Weapon(
        name="Sword",
        range="-",
        attacks=2,
        ap=0,
        armory=armory,
    )
    weapon_b = models.Weapon(
        name="Rifle",
        range="24\"",
        attacks=1,
        ap=1,
        armory=armory,
    )

    armies._apply_unit_form_data(
        unit,
        name="Test",
        quality=4,
        defense=3,
        toughness=4,
        passive_items=[],
        active_items=[],
        aura_items=[],
        weapon_entries=[
            (weapon_a, True, 1),
            (weapon_b, True, 1),
        ],
        db=DummySession(),
    )

    assert len(unit.weapon_links) == 2
    assert all(isinstance(link, models.UnitWeapon) for link in unit.weapon_links)
    assert [link.is_primary for link in unit.weapon_links] == [True, True]
    assert unit.default_weapon is weapon_a
