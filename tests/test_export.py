from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.routers import export


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
        }
    )

    roster = DummyRoster()

    monkeypatch.setattr(export, "_load_roster_for_export", lambda db, roster_id: roster)
    monkeypatch.setattr(export, "_ensure_roster_view_access", lambda roster, user: None)
    monkeypatch.setattr(export.costs, "ensure_cached_costs", lambda units: None)
    monkeypatch.setattr(export.costs, "roster_total", lambda roster: 123)
    monkeypatch.setattr(export, "_export_roster_unit_entries", lambda db, roster: [{"unit": "entry"}])
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
