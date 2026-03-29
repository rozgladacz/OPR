from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.db import Base
from app.routers import rosters


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _payload(response) -> dict[str, object]:
    return json.loads(response.body.decode("utf-8"))


def _json_request() -> Request:
    return Request({"type": "http", "method": "POST", "headers": [(b"accept", b"application/json")]})


def test_update_api_contract_returns_frontend_render_fields() -> None:
    session = _session()
    try:
        user = models.User(username="render-owner", password_hash="x")
        ruleset = models.RuleSet(name="Render Rules")
        armory = models.Armory(name="Render Armory", owner=user)
        session.add_all([user, ruleset, armory])
        session.flush()

        weapon = models.Weapon(armory=armory, name="Rifle", range='18"', attacks=1, ap=0)
        session.add(weapon)
        session.flush()

        army = models.Army(name="Render Army", owner=user, ruleset=ruleset, armory=armory)
        session.add(army)
        session.flush()

        unit = models.Unit(
            army=army,
            owner=user,
            name="Line",
            quality=4,
            defense=4,
            toughness=1,
            flags="Wojownik",
            default_weapon=weapon,
            typical_models=1,
            position=0,
        )
        session.add(unit)
        session.flush()

        session.add(models.UnitWeapon(unit=unit, weapon=weapon, is_default=True, default_count=1, is_primary=True, position=0))

        roster = models.Roster(name="Render Roster", army=army, owner=user)
        session.add(roster)
        session.flush()

        roster_unit = models.RosterUnit(roster=roster, unit=unit, count=2, position=0)
        session.add(roster_unit)
        session.flush()

        response = rosters.update_roster_unit(
            roster.id,
            roster_unit.id,
            request=_json_request(),
            count=2,
            loadout_json=json.dumps({"mode": "total", "passive": {"wojownik": 1}}, ensure_ascii=False),
            custom_name="Line Prime",
            db=session,
            current_user=user,
        )
        payload = _payload(response)

        assert set(payload) == {"unit", "units", "warnings", "total_cost", "lock_pairs"}
        unit_payload = payload["unit"]
        assert unit_payload["id"] == roster_unit.id
        assert unit_payload["custom_name"] == "Line Prime"
        assert isinstance(unit_payload["cached_cost"], (float, int))
        assert isinstance(unit_payload["loadout_json"], str)
        assert isinstance(unit_payload["loadout_summary"], str)
        assert isinstance(unit_payload["selected_passive_items"], list)
        assert isinstance(unit_payload["selected_active_items"], list)
        assert isinstance(unit_payload["selected_aura_items"], list)
        assert isinstance(payload["units"], list)
        assert isinstance(payload["total_cost"], (float, int))
    finally:
        session.close()
