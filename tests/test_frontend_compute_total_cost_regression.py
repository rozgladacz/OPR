from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


def _fixture(session):
    user = models.User(username="frontend-owner", password_hash="x")
    ruleset = models.RuleSet(name="Frontend Core")
    armory = models.Armory(name="Frontend Armory", owner=user)
    session.add_all([user, ruleset, armory])
    session.flush()

    weapon = models.Weapon(armory=armory, name="Carbine", range='24"', attacks=2, ap=1)
    ability = models.Ability(name="Scout", type="active", description="")
    session.add_all([weapon, ability])
    session.flush()

    army = models.Army(name="Frontend Army", owner=user, ruleset=ruleset, armory=armory)
    session.add(army)
    session.flush()

    unit = models.Unit(
        army=army,
        owner=user,
        name="Rangers",
        quality=4,
        defense=4,
        toughness=1,
        flags="Wojownik, Strzelec",
        default_weapon=weapon,
        typical_models=1,
        position=0,
    )
    session.add(unit)
    session.flush()

    session.add_all(
        [
            models.UnitWeapon(unit=unit, weapon=weapon, is_default=True, default_count=1, is_primary=True, position=0),
            models.UnitAbility(unit=unit, ability=ability, position=0),
        ]
    )

    roster = models.Roster(name="Frontend Roster", army=army, owner=user)
    session.add(roster)
    session.flush()

    roster_unit = models.RosterUnit(roster=roster, unit=unit, count=5, position=0)
    session.add(roster_unit)
    session.flush()
    return user, roster, roster_unit, ability


def test_quote_api_contract_contains_frontend_required_fields() -> None:
    session = _session()
    try:
        user, roster, roster_unit, ability = _fixture(session)

        response = rosters.quote_roster_unit(
            roster.id,
            roster_unit.id,
            payload={
                "count": 5,
                "loadout": {
                    "mode": "total",
                    "active": {str(ability.id): 1},
                    "passive": {"strzelec": 1},
                },
            },
            db=session,
            current_user=user,
        )
        payload = _payload(response)

        assert set(payload) == {
            "roster_unit_id",
            "unit_id",
            "count",
            "cost_engine_version",
            "warrior_total",
            "shooter_total",
            "selected_total",
            "components",
            "loadout",
        }
        assert payload["roster_unit_id"] == roster_unit.id
        assert payload["unit_id"] == roster_unit.id
        assert isinstance(payload["selected_total"], (float, int))
        assert isinstance(payload["components"], dict)
        assert set(payload["components"]) == {"base", "weapon", "active", "aura", "passive"}
        assert isinstance(payload["loadout"], dict)
        assert payload["loadout"]["mode"] == "total"
    finally:
        session.close()
