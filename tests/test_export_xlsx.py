from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import export_xlsx
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


class DummyRosterUnit:
    def __init__(self, *, count: int, cached_cost: float) -> None:
        self.count = count
        self.cached_cost = cached_cost


class DummyRoster:
    def __init__(self, roster_units: list[DummyRosterUnit]) -> None:
        self.roster_units = roster_units
        self.army = None


def test_export_xlsx_refreshes_cached_costs_before_building_entries_and_total(monkeypatch) -> None:
    roster_unit = DummyRosterUnit(count=4, cached_cost=10.0)
    roster = DummyRoster([roster_unit])

    monkeypatch.setattr(export_xlsx, "_load_roster_for_export", lambda db, roster_id: roster)
    monkeypatch.setattr(export_xlsx, "_ensure_roster_view_access", lambda roster, user: None)
    monkeypatch.setattr(export_xlsx.costs, "roster_unit_cost", lambda ru: ru.count * 11.6)
    monkeypatch.setattr(
        export_xlsx,
        "_roster_unit_export_data",
        lambda ru, unit_cache=None: {
            "rounded_total_cost": export_xlsx.utils.round_points(ru.cached_cost),
            "total_cost": ru.cached_cost,
            "weapon_details": [],
            "custom_name": None,
            "unit_name": "U",
            "count": 1,
            "quality": 4,
            "defense": 4,
            "toughness": 1,
            "passive_labels": [],
            "active_labels": [],
            "aura_labels": [],
            "weapon_summary": "",
        },
    )
    monkeypatch.setattr(export_xlsx, "_army_spell_entries", lambda roster, entries: [])
    monkeypatch.setattr(export_xlsx, "_army_rule_labels", lambda army: [])

    captured: dict[str, object] = {}

    def fake_append_roster_sheet(workbook, entries, spells, army_rules=None):
        captured["entries"] = entries
        return sum(float(entry["total_cost"]) for entry in entries)

    monkeypatch.setattr(export_xlsx, "_append_roster_sheet", fake_append_roster_sheet)
    monkeypatch.setattr(export_xlsx, "_append_weapons_sheet", lambda workbook, entries, army_rules=None: None)

    response = export_xlsx.export_xlsx(1, db=None, current_user="user")

    refreshed_cost = 4 * 11.6
    assert roster_unit.cached_cost == refreshed_cost
    assert captured["entries"][0]["rounded_total_cost"] == export_xlsx.utils.round_points(refreshed_cost)
    assert response.headers["content-disposition"].endswith(f"_{export_xlsx.utils.round_points(refreshed_cost)}.xlsx")
