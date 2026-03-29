from __future__ import annotations

import json
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.db import Base
from app.routers import rosters
from app.services import costs


SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "quote_snapshots"


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _json_response_payload(response) -> dict[str, object]:
    return json.loads(response.body.decode("utf-8"))


def _request_with_json_accept() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"accept", b"application/json")],
        }
    )


def _build_roster_fixture(session):
    user = models.User(username="owner", password_hash="secret")
    ruleset = models.RuleSet(name="Core")
    armory = models.Armory(name="Armory", owner=user)
    session.add_all([user, ruleset, armory])
    session.flush()

    rifle = models.Weapon(armory=armory, name="Rifle", range='18"', attacks=2, ap=1)
    blade = models.Weapon(armory=armory, name="Blade", range="Melee", attacks=1, ap=1)
    session.add_all([rifle, blade])
    session.flush()

    active_scout = models.Ability(name="Zasadzka", type="active", description="")
    active_fly = models.Ability(name="Samolot", type="active", description="")
    aura_heavy = models.Ability(name="Ociężałość", type="aura", description="")
    session.add_all([active_scout, active_fly, aura_heavy])
    session.flush()

    army = models.Army(name="Alpha", owner=user, ruleset=ruleset, armory=armory)
    session.add(army)
    session.flush()

    unit = models.Unit(
        army=army,
        owner=user,
        name="Veterans",
        quality=4,
        defense=4,
        toughness=3,
        typical_models=1,
        flags="Wojownik, Strzelec, Masywny, Otwarty Transport(2), Odwody",
        default_weapon=rifle,
        position=0,
    )
    session.add(unit)
    session.flush()

    session.add_all(
        [
            models.UnitWeapon(
                unit=unit,
                weapon=rifle,
                is_default=True,
                default_count=1,
                is_primary=True,
                position=0,
            ),
            models.UnitWeapon(
                unit=unit,
                weapon=blade,
                is_default=False,
                default_count=0,
                position=1,
            ),
            models.UnitAbility(unit=unit, ability=active_scout, position=0),
            models.UnitAbility(unit=unit, ability=active_fly, position=1),
            models.UnitAbility(unit=unit, ability=aura_heavy, position=2),
        ]
    )

    support = models.Unit(
        army=army,
        owner=user,
        name="Support",
        quality=5,
        defense=5,
        toughness=1,
        typical_models=1,
        flags="Wojownik",
        default_weapon=blade,
        position=1,
    )
    session.add(support)
    session.flush()

    session.add(
        models.UnitWeapon(
            unit=support,
            weapon=blade,
            is_default=True,
            default_count=1,
            is_primary=True,
            position=0,
        )
    )

    roster = models.Roster(name="List", army=army, owner=user)
    session.add(roster)
    session.flush()

    unit_a = models.RosterUnit(roster=roster, unit=unit, count=3, position=0)
    unit_b = models.RosterUnit(roster=roster, unit=support, count=2, position=1)
    session.add_all([unit_a, unit_b])
    session.flush()

    session.refresh(unit_a)
    session.refresh(unit_b)
    return {
        "user": user,
        "roster": roster,
        "unit_a": unit_a,
        "unit_b": unit_b,
        "ids": {
            "blade": blade.id,
            "scout": active_scout.id,
            "fly": active_fly.id,
            "heavy": aura_heavy.id,
        },
    }


def _assert_snapshot(snapshot_name: str, payload: dict[str, object]) -> None:
    snapshot_path = SNAPSHOT_DIR / f"{snapshot_name}.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload == expected


def test_quote_endpoint_handles_modes_dynamic_passives_and_classification() -> None:
    session = _session()
    try:
        fixture = _build_roster_fixture(session)
        roster = fixture["roster"]
        roster_unit = fixture["unit_a"]
        ids = fixture["ids"]

        base_response = rosters.quote_roster_unit(
            roster.id,
            roster_unit.id,
            payload={
                "count": 3,
                "loadout": {
                    "mode": "per_model",
                    "passive": {"wojownik": 1, "odwody": 1, "otwarty_transport(2)": 1},
                },
            },
            db=session,
            current_user=fixture["user"],
        )
        base_payload = _json_response_payload(base_response)

        blocked_odwody_response = rosters.quote_roster_unit(
            roster.id,
            roster_unit.id,
            payload={
                "count": 3,
                "loadout": {
                    "mode": "per_model",
                    "active": {str(ids["scout"]): 1},
                    "passive": {"wojownik": 1, "odwody": 1, "otwarty_transport(2)": 1},
                },
            },
            db=session,
            current_user=fixture["user"],
        )
        blocked_payload = _json_response_payload(blocked_odwody_response)

        transport_with_fly_response = rosters.quote_roster_unit(
            roster.id,
            roster_unit.id,
            payload={
                "count": 3,
                "loadout": {
                    "mode": "per_model",
                    "active": {str(ids["fly"]): 1},
                    "aura": {str(ids["heavy"]): 1},
                    "passive": {"strzelec": 1, "otwarty_transport(2)": 1},
                    "weapons": {str(ids["blade"]): 1},
                },
            },
            db=session,
            current_user=fixture["user"],
        )
        transport_payload = _json_response_payload(transport_with_fly_response)

        assert base_payload["count"] == 3
        assert base_payload["selected_total"] >= base_payload["warrior_total"]
        assert base_payload["selected_total"] >= base_payload["shooter_total"]
        assert blocked_payload["selected_total"] != base_payload["selected_total"]
        assert transport_payload["loadout"]["mode"] == "per_model"
        assert isinstance(transport_payload["loadout"]["passive"], dict)
    finally:
        session.close()



def test_quote_endpoint_and_update_flow_persists_cached_cost_and_roster_total() -> None:
    session = _session()
    try:
        fixture = _build_roster_fixture(session)
        roster = fixture["roster"]
        roster_unit = fixture["unit_a"]
        other_unit = fixture["unit_b"]
        ids = fixture["ids"]

        loadout_payload = {
            "mode": "per_model",
            "weapons": {str(ids["blade"]): 1},
            "active": {str(ids["fly"]): 1},
            "aura": {str(ids["heavy"]): 1},
            "passive": {"strzelec": 1, "otwarty_transport(2)": 1},
        }

        quote_response = rosters.quote_roster_unit(
            roster.id,
            roster_unit.id,
            payload={"count": 4, "loadout": loadout_payload},
            db=session,
            current_user=fixture["user"],
        )
        quote_payload = _json_response_payload(quote_response)

        update_response = rosters.update_roster_unit(
            roster.id,
            roster_unit.id,
            request=_request_with_json_accept(),
            count=4,
            loadout_json=json.dumps(loadout_payload, ensure_ascii=False),
            custom_name="Veterans Prime",
            db=session,
            current_user=fixture["user"],
        )
        update_payload = _json_response_payload(update_response)

        refreshed_primary = session.get(models.RosterUnit, roster_unit.id)
        refreshed_secondary = session.get(models.RosterUnit, other_unit.id)
        assert refreshed_primary is not None
        assert refreshed_secondary is not None

        total_from_units = float(refreshed_primary.cached_cost or 0.0) + float(
            refreshed_secondary.cached_cost or 0.0
        )
        persisted_loadout = json.loads(update_payload["unit"]["loadout_json"])
        persisted_quote = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={"count": 4, "loadout": persisted_loadout},
                db=session,
                current_user=fixture["user"],
            )
        )

        assert update_payload["unit"]["id"] == roster_unit.id
        assert update_payload["unit"]["custom_name"] == "Veterans Prime"
        assert quote_payload["selected_total"] > 0
        assert update_payload["unit"]["cached_cost"] == persisted_quote["selected_total"]
        assert update_payload["total_cost"] == total_from_units
    finally:
        session.close()



def test_quote_endpoint_snapshots_for_controlled_fixtures() -> None:
    session = _session()
    try:
        fixture = _build_roster_fixture(session)
        roster = fixture["roster"]
        roster_unit = fixture["unit_a"]
        ids = fixture["ids"]

        quote_per_model = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={
                    "count": 3,
                    "loadout": {
                        "mode": "per_model",
                        "passive": {"wojownik": 1, "otwarty_transport(2)": 1},
                    },
                },
                db=session,
                current_user=fixture["user"],
            )
        )

        quote_massive_total = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={
                    "count": 3,
                    "loadout": {
                        "mode": "total",
                        "weapons": {str(ids["blade"]): 2},
                        "active": {str(ids["fly"]): 1},
                        "aura": {str(ids["heavy"]): 1},
                        "passive": {"strzelec": 1, "odwody": 1, "otwarty_transport(2)": 1},
                    },
                },
                db=session,
                current_user=fixture["user"],
            )
        )

        _assert_snapshot("quote_per_model", quote_per_model)
        _assert_snapshot("quote_massive_total", quote_massive_total)
    finally:
        session.close()


def test_quote_endpoint_coerces_zero_and_negative_count_to_one() -> None:
    session = _session()
    try:
        fixture = _build_roster_fixture(session)
        roster = fixture["roster"]
        roster_unit = fixture["unit_a"]

        quoted_zero = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={"count": 0, "loadout": {"mode": "per_model"}},
                db=session,
                current_user=fixture["user"],
            )
        )
        quoted_negative = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={"count": -3, "loadout": {"mode": "per_model"}},
                db=session,
                current_user=fixture["user"],
            )
        )
        quoted_one = _json_response_payload(
            rosters.quote_roster_unit(
                roster.id,
                roster_unit.id,
                payload={"count": 1, "loadout": {"mode": "per_model"}},
                db=session,
                current_user=fixture["user"],
            )
        )

        assert quoted_zero["count"] == 1
        assert quoted_negative["count"] == 1
        assert quoted_zero["selected_total"] == quoted_one["selected_total"]
        assert quoted_negative["selected_total"] == quoted_one["selected_total"]
    finally:
        session.close()
