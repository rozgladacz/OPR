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


def test_variant_inherits_parent_cached_cost():
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
            cached_cost=17.5,
        )
        session.add(parent_weapon)
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        clone = session.execute(
            select(models.Weapon).where(models.Weapon.armory_id == variant_armory.id)
        ).scalar_one()

        assert clone.parent_id == parent_weapon.id
        assert clone.cached_cost == parent_weapon.cached_cost
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

        assert len(select_statements) in {1, 2, 3}
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

        assert len(select_statements) in {2, 3}
        armory_select = select_statements[0]
        parent_select = select_statements[1]
        assert "FROM weapons" in armory_select
        assert "armory_id" in armory_select
        assert "FROM weapons" in parent_select
        assert "WHERE weapons.id IN" in parent_select
        if len(select_statements) >= 3:
            armory_meta_select = select_statements[2]
            assert "FROM armories" in armory_meta_select
    finally:
        session.close()


def test_weapon_tree_handles_multi_level_inheritance_without_n_plus_one():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        variant_armory = models.Armory(name="Variant", parent=base_armory)

        session.add_all([base_armory, variant_armory])
        session.flush()

        base_root = models.Weapon(armory=base_armory, name="Alpha Cannon")
        base_child = models.Weapon(armory=base_armory, name="Alpha Cannon Mk II", parent=base_root)
        session.add_all([base_root, base_child])
        session.flush()

        variant_root = models.Weapon(armory=variant_armory, name="Blade")
        variant_child = models.Weapon(armory=variant_armory, name="Blade Prime", parent=variant_root)
        variant_grandchild = models.Weapon(
            armory=variant_armory,
            name="Blade Prime Elite",
            parent=variant_child,
        )
        session.add_all([variant_root, variant_child, variant_grandchild])
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        armies_router._armory_weapons(session, variant_armory)

        with _track_statements(session) as statements:
            collection = armies_router._armory_weapons(session, variant_armory)
            tree = collection.payload

            def _flatten(nodes):
                for node in nodes:
                    yield node
                    yield from _flatten(node["children"])

            flattened = list(_flatten(tree))
            ordered_ids = [weapon.id for weapon in collection.items]

        select_statements = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
        ]

        assert len(select_statements) <= 5

        node_map = {node["id"]: node for node in flattened}
        root_node = node_map[variant_root.id]
        assert [child["id"] for child in root_node["children"]] == [variant_child.id]

        child_node = node_map[variant_child.id]
        assert [child["id"] for child in child_node["children"]] == [variant_grandchild.id]

        assert ordered_ids.index(variant_root.id) < ordered_ids.index(variant_child.id) < ordered_ids.index(
            variant_grandchild.id
        )

        external_nodes = [node for node in flattened if node["has_external_parent"]]
        assert external_nodes, "Expected at least one node inheriting from another armory"

        matching = [node for node in external_nodes if node["parent_id"] == base_root.id]
        assert matching, "Expected a clone referencing the base root weapon"
        for node in matching:
            assert node["parent_name"] == base_root.effective_name
            assert node["parent_armory_id"] == base_armory.id
            assert node["parent_armory_name"] == base_armory.name
    finally:
        session.close()


def test_variant_weapon_tree_preserves_parent_structure():
    session = _session()
    try:
        base_armory = models.Armory(name="Base")
        variant_armory = models.Armory(name="Variant", parent=base_armory)

        session.add_all([base_armory, variant_armory])
        session.flush()

        base_root = models.Weapon(armory=base_armory, name="Solar Blade")
        base_child = models.Weapon(
            armory=base_armory, name="Solar Blade Prime", parent=base_root
        )
        base_grandchild = models.Weapon(
            armory=base_armory,
            name="Solar Blade Prime Elite",
            parent=base_child,
        )
        session.add_all([base_root, base_child, base_grandchild])
        session.flush()

        utils.ensure_armory_variant_sync(session, variant_armory)
        session.flush()

        collection = armories_router._armory_weapons(session, variant_armory)

        source_to_clone: dict[int, models.Weapon] = {}
        for weapon in collection.items:
            parent = weapon.parent
            if (
                parent
                and parent.id is not None
                and parent.armory_id != weapon.armory_id
                and parent.id not in source_to_clone
            ):
                source_to_clone[parent.id] = weapon

        def _parent_lookup(nodes):
            lookup: dict[int, int | None] = {}

            def _visit(children, parent_id):
                for child in children:
                    lookup[child["id"]] = parent_id
                    _visit(child.get("children", []), child["id"])

            _visit(nodes, None)
            return lookup

        tree_parent_lookup = _parent_lookup(collection.tree)

        weapon_rows = [
            {"instance": weapon, "overrides": {}, "cost": 0, "abilities": []}
            for weapon in collection.items
        ]
        payload_tree = armories_router._weapon_tree_payload(weapon_rows)
        payload_parent_lookup = _parent_lookup(payload_tree)

        for base_weapon in (base_root, base_child, base_grandchild):
            clone = source_to_clone.get(base_weapon.id)
            assert clone is not None, "Expected clone for base weapon"

            expected_parent_id = None
            if base_weapon.parent is not None:
                clone_parent = source_to_clone.get(base_weapon.parent.id)
                assert clone_parent is not None, "Expected clone for base parent"
                expected_parent_id = clone_parent.id

            assert (
                tree_parent_lookup.get(clone.id) == expected_parent_id
            ), "ArmoryWeaponCollection tree should mirror base structure"
            assert (
                payload_parent_lookup.get(clone.id) == expected_parent_id
            ), "Weapon tree payload should mirror base structure"
    finally:
        session.close()
