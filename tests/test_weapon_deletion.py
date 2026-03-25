from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import models
from app.db import Base
from app.routers import armories as armories_router


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _fake_templates(monkeypatch):
    captured: dict[str, object] = {}

    def template_response(name, context):
        captured["name"] = name
        captured["context"] = context
        return SimpleNamespace(context=context)

    monkeypatch.setattr(armories_router, "templates", SimpleNamespace(TemplateResponse=template_response))
    return captured


def test_delete_weapon_blocks_when_unit_defaults(monkeypatch):
    session = _session()
    try:
        user = models.User(username="owner", password_hash="secret")
        ruleset = models.RuleSet(name="Core")
        armory = models.Armory(name="Base", owner=user)
        army = models.Army(name="Alpha", owner=user, ruleset=ruleset, armory=armory)
        weapon = models.Weapon(armory=armory, name="Sword", range="Melee", attacks=2, ap=1)
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

        captured = _fake_templates(monkeypatch)
        request = Request({"type": "http"})
        response = armories_router.delete_weapon(
            armory_id=armory.id,
            weapon_id=weapon.id,
            request=request,
            db=session,
            current_user=user,
        )

        assert response.context["error"] is not None
        assert weapon.id == session.get(models.Weapon, weapon.id).id
        assert captured["name"] == "armory_detail.html"
    finally:
        session.close()


def test_delete_weapon_cleans_links_and_children(monkeypatch):
    session = _session()
    try:
        user = models.User(username="owner", password_hash="secret")
        ruleset = models.RuleSet(name="Core")
        armory = models.Armory(name="Base", owner=user)
        variant = models.Armory(name="Variant", owner=user, parent=armory)
        army = models.Army(name="Alpha", owner=user, ruleset=ruleset, armory=armory)
        weapon = models.Weapon(armory=armory, name="Sword", range="Melee", attacks=2, ap=1)
        child_weapon = models.Weapon(armory=variant, parent=weapon, name="Sword Mk II")
        unit = models.Unit(
            army=army,
            owner=user,
            name="Infantry",
            quality=4,
            defense=4,
            toughness=4,
            typical_models=1,
            position=0,
        )
        unit_weapon = models.UnitWeapon(unit=unit, weapon=weapon, is_default=True)
        spell = models.ArmySpell(army=army, weapon=weapon, kind="upgrade")
        roster = models.Roster(name="List", army=army, owner=user)
        roster_unit = models.RosterUnit(roster=roster, unit=unit, count=1)

        session.add_all(
            [
                user,
                ruleset,
                armory,
                variant,
                army,
                weapon,
                child_weapon,
                unit,
                unit_weapon,
                spell,
                roster,
            ]
        )
        session.flush()
        roster_unit.extra_weapons_json = json.dumps({"weapons": {str(weapon.id): 2}})
        session.add(roster_unit)
        session.flush()

        _fake_templates(monkeypatch)
        request = Request({"type": "http"})
        response = armories_router.delete_weapon(
            armory_id=armory.id,
            weapon_id=weapon.id,
            request=request,
            db=session,
            current_user=user,
        )

        assert response.status_code == 303
        assert session.get(models.Weapon, weapon.id) is None
        assert session.get(models.Weapon, child_weapon.id) is None
        remaining_links = session.execute(select(models.UnitWeapon).where(models.UnitWeapon.unit_id == unit.id)).all()
        assert not remaining_links
        remaining_spells = session.execute(select(models.ArmySpell).where(models.ArmySpell.army_id == army.id)).all()
        assert not remaining_spells
        updated_roster_unit = session.get(models.RosterUnit, roster_unit.id)
        payload = json.loads(updated_roster_unit.extra_weapons_json)
        assert payload.get("weapons") == {}
    finally:
        session.close()
