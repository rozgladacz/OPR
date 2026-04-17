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
from app.routers import armies as armies_router


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _build_army_fixture(session):
    user = models.User(username="owner", password_hash="secret")
    ruleset = models.RuleSet(name="Core")
    armory = models.Armory(name="Armory", owner=user)
    session.add_all([user, ruleset, armory])
    session.flush()
    army = models.Army(name="Test Army", owner=user, ruleset=ruleset, armory=armory)
    session.add(army)
    session.flush()
    return {"user": user, "army": army}


def _json_payload(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def test_spell_weapon_cost_preview_returns_integer_cost() -> None:
    session = _session()
    try:
        fixture = _build_army_fixture(session)
        army = fixture["army"]
        user = fixture["user"]

        response = armies_router.spell_weapon_cost_preview(
            army.id,
            payload={"range": "18\"", "attacks": "2", "ap": "1", "abilities": []},
            db=session,
            current_user=user,
        )
        payload = _json_payload(response)

        assert "spell_cost" in payload
        assert isinstance(payload["spell_cost"], int)
        assert payload["spell_cost"] > 0
    finally:
        session.close()


def test_spell_weapon_cost_preview_with_no_payload_returns_none() -> None:
    session = _session()
    try:
        fixture = _build_army_fixture(session)
        army = fixture["army"]
        user = fixture["user"]

        response = armies_router.spell_weapon_cost_preview(
            army.id,
            payload=None,
            db=session,
            current_user=user,
        )
        payload = _json_payload(response)

        assert payload["spell_cost"] is None
    finally:
        session.close()


def test_spell_weapon_cost_preview_higher_ap_costs_more() -> None:
    session = _session()
    try:
        fixture = _build_army_fixture(session)
        army = fixture["army"]
        user = fixture["user"]

        low_ap = _json_payload(armies_router.spell_weapon_cost_preview(
            army.id,
            payload={"range": "18\"", "attacks": "2", "ap": "0", "abilities": []},
            db=session,
            current_user=user,
        ))
        high_ap = _json_payload(armies_router.spell_weapon_cost_preview(
            army.id,
            payload={"range": "18\"", "attacks": "2", "ap": "3", "abilities": []},
            db=session,
            current_user=user,
        ))

        assert high_ap["spell_cost"] > low_ap["spell_cost"]
    finally:
        session.close()


def test_spell_weapon_cost_preview_matches_internal_formula() -> None:
    session = _session()
    try:
        fixture = _build_army_fixture(session)
        army = fixture["army"]
        user = fixture["user"]

        form_values = {"range": "18\"", "attacks": "3", "ap": "2", "abilities": []}
        response = armies_router.spell_weapon_cost_preview(
            army.id,
            payload=form_values,
            db=session,
            current_user=user,
        )
        payload = _json_payload(response)

        # Verify against the internal helper directly (it applies lock-on internally)
        expected_cost = armies_router._spell_weapon_cost(None, form_values)

        assert payload["spell_cost"] == expected_cost
    finally:
        session.close()
