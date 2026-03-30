from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
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


SQLITE_TIMEOUT_SECONDS = 30


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
    session.commit()

    return {
        "user_id": user.id,
        "roster_id": roster.id,
        "primary_unit_id": unit_a.id,
        "secondary_unit_id": unit_b.id,
        "ids": {
            "blade": blade.id,
            "fly": active_fly.id,
            "heavy": aura_heavy.id,
        },
    }


def _create_session_factory(tmp_path: Path):
    db_path = tmp_path / "concurrency_stability.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": SQLITE_TIMEOUT_SECONDS},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_quote_and_update_are_stable_across_concurrent_requests_without_shared_sessions(tmp_path) -> None:
    SessionLocal = _create_session_factory(tmp_path)
    with SessionLocal() as session:
        fixture = _build_roster_fixture(session)

    loadout_payload = {
        "mode": "per_model",
        "weapons": {str(fixture["ids"]["blade"]): 1},
        "active": {str(fixture["ids"]["fly"]): 1},
        "aura": {str(fixture["ids"]["heavy"]): 1},
        "passive": {"strzelec": 1, "otwarty_transport(2)": 1},
    }

    def quote_once() -> float:
        with SessionLocal() as session:
            current_user = session.get(models.User, fixture["user_id"])
            response = rosters.quote_roster_unit(
                fixture["roster_id"],
                fixture["primary_unit_id"],
                payload={"count": 4, "loadout": loadout_payload},
                db=session,
                current_user=current_user,
            )
            return float(_json_response_payload(response)["selected_total"])

    expected_quote_total = quote_once()

    with ThreadPoolExecutor(max_workers=6) as pool:
        quote_totals = list(pool.map(lambda _idx: quote_once(), range(24)))

    assert quote_totals
    assert all(total == expected_quote_total for total in quote_totals)

    def update_once() -> tuple[float, float]:
        with SessionLocal() as session:
            current_user = session.get(models.User, fixture["user_id"])
            response = rosters.update_roster_unit(
                fixture["roster_id"],
                fixture["primary_unit_id"],
                request=_request_with_json_accept(),
                count=4,
                loadout_json=json.dumps(loadout_payload, ensure_ascii=False),
                custom_name="Veterans Prime",
                db=session,
                current_user=current_user,
            )
            payload = _json_response_payload(response)
            unit_payload = payload["unit"]
            return float(unit_payload["cached_cost"]), float(payload["total_cost"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        update_results = list(pool.map(lambda _idx: update_once(), range(12)))

    assert update_results
    assert all(cached_cost == expected_quote_total for cached_cost, _ in update_results)

    with SessionLocal() as verification_session:
        refreshed_primary = verification_session.get(
            models.RosterUnit, fixture["primary_unit_id"]
        )
        refreshed_secondary = verification_session.get(
            models.RosterUnit, fixture["secondary_unit_id"]
        )

        expected_total = float(refreshed_primary.cached_cost or 0.0) + float(
            refreshed_secondary.cached_cost or 0.0
        )
        assert all(total_cost == expected_total for _, total_cost in update_results)
        assert float(refreshed_primary.cached_cost or 0.0) == expected_quote_total
