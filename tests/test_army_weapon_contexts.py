from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app import models
from app.db import Base
from app.routers import armies as armies_router


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _seed_army(session: Session) -> tuple[models.User, models.Army, models.Unit, models.Weapon]:
    user = models.User(username="owner", password_hash="secret")
    ruleset = models.RuleSet(name="Core")
    armory = models.Armory(name="Base")
    army = models.Army(name="Alpha", owner=user, ruleset=ruleset, armory=armory)
    weapon = models.Weapon(
        armory=armory,
        name="Sword",
        range="Melee",
        attacks=2,
        ap=1,
    )
    unit = models.Unit(
        army=army,
        owner=user,
        name="Infantry",
        quality=4,
        defense=4,
        toughness=4,
        typical_models=1,
        position=0,
        default_weapon=weapon,
    )

    session.add_all([user, ruleset, armory, army, weapon, unit])
    session.flush()

    return user, army, unit, weapon


def _fake_templates(monkeypatch):
    captured: dict[str, object] = {}

    def template_response(name, context):
        captured["name"] = name
        captured["context"] = context
        return SimpleNamespace(context=context)

    monkeypatch.setattr(armies_router, "templates", SimpleNamespace(TemplateResponse=template_response))
    return captured


def test_edit_unit_form_uses_single_armory_weapon_collection(monkeypatch):
    session = _session()
    try:
        user, army, unit, weapon = _seed_army(session)
        captured = _fake_templates(monkeypatch)

        request = Request({"type": "http"})
        armies_router.edit_unit_form(
            army_id=army.id,
            unit_id=unit.id,
            request=request,
            db=session,
            current_user=user,
        )

        context = captured["context"]
        assert any(item.id == weapon.id for item in context["weapons"])
        assert any(entry["id"] == weapon.id for entry in context["weapon_choices"])
        assert any(entry["id"] == weapon.id for entry in context["weapon_tree"]["flat"])
    finally:
        session.close()


def test_render_army_edit_uses_single_armory_weapon_collection(monkeypatch):
    session = _session()
    try:
        user, army, _, weapon = _seed_army(session)
        captured = _fake_templates(monkeypatch)

        request = Request({"type": "http"})
        armies_router._render_army_edit(
            request=request,
            db=session,
            army=army,
            current_user=user,
        )

        context = captured["context"]
        assert any(item.id == weapon.id for item in context["weapons"])
        assert any(entry["id"] == weapon.id for entry in context["weapon_choices"])
        assert any(entry["id"] == weapon.id for entry in context["weapon_tree"]["flat"])
    finally:
        session.close()
