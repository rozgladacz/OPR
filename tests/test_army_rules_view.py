from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import armies
from app.services import army_rules


def test_army_rules_picker_omits_toggle_controls() -> None:
    app = Starlette()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    request = Request(
        {"type": "http", "method": "GET", "path": "/armies/1/rules", "app": app, "headers": []}
    )

    army = models.Army(
        name="Test Army",
        parent_id=None,
        owner_id=1,
        ruleset_id=1,
        armory_id=1,
        passive_rules=army_rules.serialize_rules(
            [
                {
                    "slug": "nieustraszony",
                    "label": "Nieustraszony",
                    "is_default": False,
                    "is_mandatory": True,
                }
            ]
        ),
    )

    user = SimpleNamespace(username="tester", is_admin=True)
    context = armies._army_rules_context(request, army, user)
    html = armies.templates.get_template("army_rules.html").render(context)

    assert 'data-default-toggle="true"' not in html
    assert 'data-mandatory-toggle="true"' not in html
    assert 'data-default-initial="true"' not in html
    assert 'data-mandatory-initial="true"' not in html
