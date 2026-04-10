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
