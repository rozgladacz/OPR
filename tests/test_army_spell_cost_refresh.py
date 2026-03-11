from __future__ import annotations

import math

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import models
from app.db import Base
from app.routers import armies


def _session():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_spell_page_context_recalculates_weapon_spell_cost() -> None:
    session = _session()
    try:
        user = models.User(username='owner', password_hash='secret')
        ruleset = models.RuleSet(name='Core')
        armory = models.Armory(name='Base')
        army = models.Army(name='Alpha', owner=user, ruleset=ruleset, armory=armory)
        weapon = models.Weapon(armory=armory, army=army, name='Kostur', range='18"', attacks=1, ap=3)
        spell = models.ArmySpell(
            army=army,
            kind='weapon',
            weapon=weapon,
            base_label='stary',
            description='stary opis',
            cost=1,
            position=1,
        )
        session.add_all([user, ruleset, armory, army, weapon, spell])
        session.flush()

        request = Request({'type': 'http'})
        context = armies._spell_page_context(request, army, user, session)

        [refreshed] = context['spells']
        expected_cost = int(math.ceil(max(armies.costs.weapon_cost(weapon, unit_quality=4), 0.0) / 7.0))
        assert refreshed.cost == expected_cost
        assert refreshed.base_label != 'stary'
        assert refreshed.description != 'stary opis'
    finally:
        session.close()
