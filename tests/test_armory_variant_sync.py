from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.services import utils
from app.routers import armies as armies_router
from app.routers import armories as armories_router


@contextmanager
def _track_statements(session):
    statements: list[str] = []

    def before_execute(_, __, statement, ___, ____, _____):
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", before_execute)
    try:
        yield statements
    finally:
        event.remove(session.bind, "before_cursor_execute", before_execute)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_variant_inherits_new_weapon_without_overrides():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        variant_armory = models.Armory(name="Variant", parent=base_armory)

        session.add_all([base_armory, variant_armory])
        session.flush()

        parent_weapon = models.Weapon(
            armory=base_armory,
            name="Sword",
            range="Melee",
            attacks=3,
            ap=2,
        )
        session.add(parent_weapon)
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        clone = session.execute(
            select(models.Weapon).where(models.Weapon.armory_id == variant_armory.id)
        ).scalar_one()

        assert clone.parent_id == parent_weapon.id
        assert clone.attacks is None
        assert clone.ap is None
        assert clone.effective_attacks == parent_weapon.attacks
        assert clone.effective_ap == parent_weapon.ap
    finally:
        session.close()


def test_nested_variant_keeps_parent_defaults():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        first_variant = models.Armory(name="Variant A", parent=base_armory)
        second_variant = models.Armory(name="Variant B", parent=first_variant)

        session.add_all([base_armory, first_variant, second_variant])
        session.flush()

        parent_weapon = models.Weapon(
            armory=base_armory,
            name="Axe",
            range="Melee",
            attacks=5,
            ap=-1,
        )
        session.add(parent_weapon)
        session.flush()

        utils.ensure_armory_variant_sync(session, first_variant)
        utils.ensure_armory_variant_sync(session, second_variant)
        session.flush()

        first_clone = session.execute(
            select(models.Weapon).where(models.Weapon.armory_id == first_variant.id)
        ).scalar_one()
        second_clone = session.execute(
            select(models.Weapon).where(models.Weapon.armory_id == second_variant.id)
        ).scalar_one()

        assert first_clone.attacks is None
        assert first_clone.ap is None
        assert second_clone.attacks is None
        assert second_clone.ap is None
        assert second_clone.parent_id == first_clone.id
        assert second_clone.effective_attacks == parent_weapon.attacks
        assert second_clone.effective_ap == parent_weapon.ap
    finally:
        session.close()


def test_army_view_variant_sync_cached_in_session():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        variant_armory = models.Armory(name="Variant", parent=base_armory)

        session.add_all([base_armory, variant_armory])
        session.flush()

        parent_weapon = models.Weapon(
            armory=base_armory,
            name="Sword",
            range="Melee",
            attacks=3,
            ap=2,
        )
        session.add(parent_weapon)
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        armies_router._armory_weapons(session, variant_armory)

        with _track_statements(session) as statements:
            armies_router._armory_weapons(session, variant_armory)

        select_statements = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
        ]

        assert len(select_statements) in {1, 2}
        armory_select = select_statements[0]
        assert "FROM weapons" in armory_select
        assert "armory_id" in armory_select
        if len(select_statements) == 2:
            parent_select = select_statements[1]
            assert "FROM weapons" in parent_select
            assert "WHERE weapons.id IN" in parent_select
    finally:
        session.close()


def test_armory_view_variant_sync_cached_in_session():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        variant_armory = models.Armory(name="Variant", parent=base_armory)

        session.add_all([base_armory, variant_armory])
        session.flush()

        parent_weapon = models.Weapon(
            armory=base_armory,
            name="Axe",
            range="Melee",
            attacks=5,
            ap=-1,
        )
        session.add(parent_weapon)
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        armories_router._armory_weapons(session, variant_armory)

        with _track_statements(session) as statements:
            utils.ensure_armory_variant_sync(session, variant_armory)
            armories_router._armory_weapons(session, variant_armory)

        select_statements = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
        ]

        assert len(select_statements) == 2
        armory_select, parent_select = select_statements
        assert "FROM weapons" in armory_select
        assert "armory_id" in armory_select
        assert "FROM weapons" in parent_select
        assert "WHERE weapons.id IN" in parent_select
    finally:
        session.close()
