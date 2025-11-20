from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers.export import _army_rule_labels
from app.routers.export_xlsx import _append_roster_sheet, _append_weapons_sheet


def test_army_rules_rendered_in_xlsx_header() -> None:
    army = models.Army(
        name="Test Army",
        parent_id=None,
        owner_id=None,
        ruleset_id=1,
        armory_id=1,
        passive_rules="Nieustraszony",
    )

    workbook = Workbook()
    rules = _army_rule_labels(army)

    _append_roster_sheet(workbook, [], spells=None, army_rules=rules)
    _append_weapons_sheet(workbook, [], army_rules=rules)

    expected = f"Zasady armii: {', '.join(rules)}"
    assert workbook["Lista"]["A1"].value == expected
    assert workbook["Zbrojownia"]["A1"].value == expected
