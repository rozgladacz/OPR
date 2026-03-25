from dataclasses import dataclass
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import armies  # noqa: E402


@dataclass
class DummyUnit:
    id: int
    position: int = 0


def test_move_unit_in_sequence_handles_equal_positions() -> None:
    units = [DummyUnit(id=1, position=0), DummyUnit(id=2, position=0), DummyUnit(id=3, position=0)]

    moved = armies._move_unit_in_sequence(units, 2, "down")

    assert moved is True
    assert [unit.id for unit in units] == [1, 3, 2]

    armies._resequence_army_units(units)

    assert [unit.position for unit in units] == [0, 1, 2]


def test_move_unit_in_sequence_prevents_out_of_range_moves() -> None:
    units = [DummyUnit(id=1, position=0), DummyUnit(id=2, position=1)]

    assert armies._move_unit_in_sequence(units, 1, "up") is False
    assert armies._move_unit_in_sequence(units, 2, "down") is False
    assert [unit.id for unit in units] == [1, 2]


@dataclass
class DummySpell:
    id: int
    position: int = 0


def test_move_spell_in_sequence_handles_equal_positions() -> None:
    spells = [DummySpell(id=11, position=0), DummySpell(id=12, position=0), DummySpell(id=13, position=0)]

    moved = armies._move_unit_in_sequence(spells, 12, "up")

    assert moved is True
    assert [spell.id for spell in spells] == [12, 11, 13]


def test_move_spell_in_sequence_rejects_invalid_direction() -> None:
    spells = [DummySpell(id=11, position=0), DummySpell(id=12, position=1)]

    assert armies._move_unit_in_sequence(spells, 11, "left") is False
    assert [spell.id for spell in spells] == [11, 12]
