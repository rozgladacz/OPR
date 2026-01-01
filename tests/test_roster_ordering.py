import pytest

from app.routers import rosters
from app import models


def _roster_unit(unit_id: int, position: int | None = None) -> models.RosterUnit:
    unit = models.RosterUnit(id=unit_id, roster_id=1, unit_id=unit_id)
    if position is not None:
        unit.position = position
    return unit


def test_apply_roster_order_updates_positions() -> None:
    units = [_roster_unit(1, 0), _roster_unit(2, 1), _roster_unit(3, 2)]

    changed = rosters._apply_roster_order(units, [3, 1, 2])

    assert changed is True
    positions = {unit.id: unit.position for unit in units}
    assert positions == {3: 0, 1: 1, 2: 2}


def test_apply_roster_order_rejects_invalid_entries() -> None:
    units = [_roster_unit(1), _roster_unit(2)]

    with pytest.raises(ValueError):
        rosters._apply_roster_order(units, [1])
