from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models  # noqa: E402
from app.db import Base  # noqa: E402
from app.routers import rosters  # noqa: E402


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)


def _seed_army(session: Session, owner_id: int | None = None) -> models.Army:
    ruleset = models.RuleSet(name=f"Ruleset-{owner_id or 'global'}")
    armory = models.Armory(name="Armory", owner_id=owner_id)
    army = models.Army(name="Army", armory=armory, owner_id=owner_id, ruleset=ruleset)
    session.add_all([ruleset, armory, army])
    session.commit()
    session.refresh(army)
    return army


def test_admin_can_create_global_roster() -> None:
    session = _build_session()
    army = _seed_army(session)
    admin_user = SimpleNamespace(id=10, is_admin=True)

    response = rosters.create_roster(
        request=SimpleNamespace(),
        name="Globalna",
        army_id=army.id,
        points_limit="1000",
        is_global="on",
        db=session,
        current_user=admin_user,
    )

    created = session.query(models.Roster).one()
    assert created.owner_id is None
    assert response.status_code == status.HTTP_303_SEE_OTHER


def test_non_admin_cannot_create_global_roster() -> None:
    session = _build_session()
    user_id = 22
    army = _seed_army(session, owner_id=user_id)
    normal_user = SimpleNamespace(id=user_id, is_admin=False)

    try:
        rosters.create_roster(
            request=SimpleNamespace(),
            name="Globalna",
            army_id=army.id,
            points_limit="1000",
            is_global="on",
            db=session,
            current_user=normal_user,
        )
    except HTTPException as exc:
        assert exc.status_code == status.HTTP_403_FORBIDDEN
    else:  # pragma: no cover - safety
        assert False, "Expected HTTPException for non-admin user"
