import sys
from pathlib import Path

import pytest
from starlette.datastructures import URL
from starlette.requests import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import models
from app.db import Base
from app.routers import armories as armories_router
from app.services import utils


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()

class _DummyURL:
    def __init__(self, path: str):
        self._path = path

    def make_absolute_url(self, base_url: URL) -> URL:
        return base_url.replace(path=self._path)

    def __str__(self) -> str:
        return self._path


class _DummyApp:
    def url_path_for(self, name: str, **path_params: str) -> _DummyURL:
        path = path_params.get("path")
        if path:
            return _DummyURL(path)
        return _DummyURL(f"/{name}")


async def _empty_receive() -> dict:
    return {"type": "http.request"}


def _build_request(path: str = "/armories/1") -> Request:
    dummy_app = _DummyApp()
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "app": dummy_app,
        "router": dummy_app,
    }
    return Request(scope, _empty_receive)


def test_refresh_costs_only_updates_missing_entries(monkeypatch):
    session = _session()
    try:
        armory = models.Armory(name="Base")
        weapon_with_cache = models.Weapon(
            armory=armory,
            name="Cached",
            range="Melee",
            attacks=2,
            ap=1,
            cached_cost=7.5,
        )
        weapon_without_cache = models.Weapon(
            armory=armory,
            name="Missing",
            range="Melee",
            attacks=3,
            ap=0,
        )
        weapon_with_invalid_cache = models.Weapon(
            armory=armory,
            name="Invalid",
            range="Melee",
            attacks=4,
            ap=-1,
            cached_cost=float("nan"),
        )

        session.add_all(
            [armory, weapon_with_cache, weapon_without_cache, weapon_with_invalid_cache]
        )
        session.flush()

        recorded_calls: list[str] = []

        def fake_weapon_cost(weapon: models.Weapon) -> float:
            recorded_calls.append(weapon.name or "")
            return {"Missing": 11.0, "Invalid": 12.0}.get(weapon.name or "", 0.0)

        monkeypatch.setattr(armories_router.costs, "weapon_cost", fake_weapon_cost)

        armories_router._refresh_costs(
            session, [weapon_with_cache, weapon_without_cache, weapon_with_invalid_cache]
        )

        assert recorded_calls == ["Missing", "Invalid"]
        assert weapon_without_cache.cached_cost == pytest.approx(11.0)
        assert weapon_with_invalid_cache.cached_cost == pytest.approx(12.0)
        assert weapon_with_cache.cached_cost == pytest.approx(7.5)
    finally:
        session.close()


def test_view_armory_uses_cached_cost_without_recomputation(monkeypatch):
    session = _session()
    try:
        user = models.User(username="viewer", password_hash="x", is_admin=False)
        armory = models.Armory(name="Showcase", owner=user)
        weapon = models.Weapon(
            armory=armory,
            owner=user,
            name="Halberd",
            range="Melee",
            attacks=3,
            ap=1,
            cached_cost=15.0,
        )

        session.add_all([user, armory, weapon])
        session.flush()

        recorded_calls: list[int] = []

        def fake_weapon_cost(weapon: models.Weapon) -> float:
            recorded_calls.append(weapon.id or -1)
            return 99.0

        monkeypatch.setattr(armories_router.costs, "weapon_cost", fake_weapon_cost)

        request = _build_request(path=f"/armories/{armory.id}")
        response = armories_router.view_armory(
            armory.id, request, session, current_user=user
        )

        assert recorded_calls == []
        weapon_rows = response.context["weapons"]
        assert len(weapon_rows) == 1
        assert weapon_rows[0]["cost"] == pytest.approx(15.0)
    finally:
        session.close()


def test_view_armory_falls_back_to_cost_when_cache_missing(monkeypatch):
    session = _session()
    try:
        user = models.User(username="admin", password_hash="x", is_admin=True)
        base_armory = models.Armory(name="Base", owner=user)
        variant_armory = models.Armory(name="Variant", owner=user, parent=base_armory)
        parent_weapon = models.Weapon(
            armory=base_armory,
            owner=user,
            name="Spear",
            range="Melee",
            attacks=2,
            ap=0,
        )

        session.add_all([user, base_armory, variant_armory, parent_weapon])
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        variant_weapon = session.execute(
            select(models.Weapon).where(models.Weapon.armory_id == variant_armory.id)
        ).scalar_one()

        recorded_calls: list[int] = []

        def fake_weapon_cost(weapon: models.Weapon) -> float:
            recorded_calls.append(weapon.id or -1)
            return 21.0

        monkeypatch.setattr(armories_router.costs, "weapon_cost", fake_weapon_cost)

        request = _build_request(path=f"/armories/{variant_armory.id}")
        response = armories_router.view_armory(
            variant_armory.id, request, session, current_user=user
        )

        assert recorded_calls == [variant_weapon.id]
        weapon_rows = response.context["weapons"]
        assert len(weapon_rows) == 1
        assert weapon_rows[0]["cost"] == pytest.approx(21.0)
    finally:
        session.close()
