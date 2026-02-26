from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import export, rosters


class DummyRoster:
    def __init__(self) -> None:
        self.roster_units = []
        self.name = "Test roster"
        self.army = "Test army"
        self.points_limit = None


def test_roster_print_context_keys(monkeypatch) -> None:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/rosters/1/print",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": app,
            "router": app.router,
        }
    )

    roster = DummyRoster()

    monkeypatch.setattr(export, "_load_roster_for_export", lambda db, roster_id: roster)
    monkeypatch.setattr(export, "_ensure_roster_view_access", lambda roster, user: None)
    monkeypatch.setattr(export.costs, "update_cached_costs", lambda units: None)
    monkeypatch.setattr(
        export,
        "_export_roster_unit_entries",
        lambda db, roster: [{"unit": "entry", "total_cost": 123.0}],
    )
    monkeypatch.setattr(export, "_army_spell_entries", lambda roster, entries: [{"label": "Spell"}])
    monkeypatch.setattr(export, "_army_rule_labels", lambda army: ["Rule A"])

    response = export.roster_print(1, request, db=None, current_user="user")

    expected_keys = {
        "request",
        "user",
        "roster",
        "roster_items",
        "total_cost",
        "total_cost_rounded",
        "generated_at",
        "spell_entries",
        "army_rules",
    }

    assert expected_keys.issubset(response.context.keys())


class DummyRosterUnit:
    def __init__(self, *, count: int, cached_cost: float) -> None:
        self.count = count
        self.cached_cost = cached_cost


def test_roster_export_list_refreshes_cached_costs_before_total_and_entries(monkeypatch) -> None:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/rosters/1/export/lista",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": app,
            "router": app.router,
        }
    )

    roster = DummyRoster()
    roster_unit = DummyRosterUnit(count=3, cached_cost=10.0)
    roster.roster_units = [roster_unit]

    monkeypatch.setattr(export, "_load_roster_for_export", lambda db, roster_id: roster)
    monkeypatch.setattr(export, "_ensure_roster_view_access", lambda roster, user: None)
    monkeypatch.setattr(export.costs, "roster_unit_cost", lambda ru: ru.count * 12.4)
    monkeypatch.setattr(
        export,
        "_export_roster_unit_entries",
        lambda db, roster: [
            {
                "rounded_total_cost": export.utils.round_points(roster.roster_units[0].cached_cost),
                "total_cost": roster.roster_units[0].cached_cost,
            }
        ],
    )
    monkeypatch.setattr(export, "_army_spell_entries", lambda roster, entries: [])
    monkeypatch.setattr(export, "_army_rule_labels", lambda army: [])

    response = export.roster_export_list(1, request, db=None, current_user="user")

    refreshed_cost = 3 * 12.4
    assert roster_unit.cached_cost == refreshed_cost
    assert response.context["total_cost"] == refreshed_cost
    assert response.context["total_cost_rounded"] == export.utils.round_points(refreshed_cost)
    assert response.context["entries"][0]["rounded_total_cost"] == export.utils.round_points(refreshed_cost)


def test_roster_unit_export_data_uses_loadout_totals_instead_of_cached_cost(monkeypatch) -> None:
    unit = SimpleNamespace(
        id=1,
        name="Unit",
        quality=4,
        defense=4,
        toughness=1,
        flags="",
        army=None,
    )
    roster_unit = SimpleNamespace(
        unit=unit,
        cached_cost=999.0,
        count=1,
        custom_name=None,
        selected_weapons="",
        selected_abilities="",
    )

    monkeypatch.setattr(rosters, "_unit_weapon_options", lambda _unit: [])
    monkeypatch.setattr(rosters, "_passive_entries", lambda _unit: [])
    monkeypatch.setattr(rosters, "_ability_entries", lambda _unit, _kind: [])
    monkeypatch.setattr(rosters, "_default_loadout_summary", lambda _unit: "")
    monkeypatch.setattr(rosters, "_roster_unit_loadout", lambda _ru, **kwargs: {"mode": "per_model"})
    monkeypatch.setattr(rosters, "_roster_unit_classification", lambda _ru, _loadout: None)
    monkeypatch.setattr(rosters.costs, "roster_unit_role_totals", lambda _ru, _loadout: {"wojownik": 41.0, "strzelec": 58.0})
    monkeypatch.setattr(
        rosters.costs,
        "roster_unit_cost",
        lambda _ru: (_ for _ in ()).throw(AssertionError("cached/legacy cost path should not be used")),
    )

    entry = rosters._roster_unit_export_data(roster_unit, loadout_override={"mode": "per_model"})

    assert entry["total_cost"] == 58.0
    assert entry["rounded_total_cost"] == export.utils.round_points(58.0)
