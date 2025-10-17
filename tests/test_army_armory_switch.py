import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import selectinload, sessionmaker
from starlette.requests import Request

from app import models
from app.db import Base
from app.routers import armies as armies_router
from app.services import utils


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_switch_army_armory_updates_units_and_rosters():
    session = _session()
    try:
        user = models.User(username="owner", password_hash="secret")
        ruleset = models.RuleSet(name="Core")
        base_armory = models.Armory(name="Base")
        armory_a = models.Armory(name="First", parent=base_armory, owner=user)
        armory_b = models.Armory(name="Second", parent=base_armory, owner=user)
        session.add_all([user, ruleset, base_armory, armory_a, armory_b])
        session.flush()

        base_sword = models.Weapon(
            armory=base_armory,
            name="Sword",
            range="Melee",
            attacks=3,
            ap=1,
        )
        base_blaster = models.Weapon(
            armory=base_armory,
            name="Blaster",
            range="24",
            attacks=2,
            ap=0,
        )
        session.add_all([base_sword, base_blaster])
        session.flush()

        utils.ensure_armory_variant_sync(session, armory_a)
        utils.ensure_armory_variant_sync(session, armory_b)
        session.flush()

        sword_a = session.execute(
            select(models.Weapon).where(
                models.Weapon.armory_id == armory_a.id,
                models.Weapon.parent_id == base_sword.id,
            )
        ).scalar_one()
        sword_b = session.execute(
            select(models.Weapon).where(
                models.Weapon.armory_id == armory_b.id,
                models.Weapon.parent_id == base_sword.id,
            )
        ).scalar_one()

        name_match_a = models.Weapon(
            armory=armory_a,
            name="Repeater",
            range="18",
            attacks=3,
            ap=0,
        )
        name_match_b = models.Weapon(
            armory=armory_b,
            name="repeater",
            range="18",
            attacks=3,
            ap=0,
        )
        unmatched_weapon_a = models.Weapon(
            armory=armory_a,
            name="Obsolete",
            range="12",
            attacks=1,
            ap=0,
        )
        session.add_all([name_match_a, name_match_b, unmatched_weapon_a])
        session.flush()

        army = models.Army(name="Alpha", owner=user, ruleset=ruleset, armory=armory_a)
        session.add(army)
        session.flush()

        custom_weapon = models.Weapon(
            armory=armory_a,
            army=army,
            name="Custom Staff",
            range="Melee",
            attacks=1,
            ap=0,
        )
        session.add(custom_weapon)
        session.flush()

        unit = models.Unit(
            army=army,
            owner=user,
            name="Infantry",
            quality=4,
            defense=4,
            toughness=4,
            typical_models=1,
            position=0,
            default_weapon=sword_a,
        )
        session.add(unit)
        session.flush()

        session.add_all(
            [
                models.UnitWeapon(
                    unit=unit,
                    weapon=sword_a,
                    default_count=1,
                    is_default=True,
                    is_primary=True,
                    position=0,
                ),
                models.UnitWeapon(
                    unit=unit,
                    weapon=name_match_a,
                    default_count=2,
                    is_default=True,
                    position=1,
                ),
                models.UnitWeapon(
                    unit=unit,
                    weapon=unmatched_weapon_a,
                    default_count=1,
                    is_default=True,
                    position=2,
                ),
                models.UnitWeapon(
                    unit=unit,
                    weapon=custom_weapon,
                    default_count=1,
                    is_default=True,
                    position=3,
                ),
            ]
        )

        roster = models.Roster(name="List", army=army, owner=user)
        session.add(roster)
        session.flush()

        roster_unit = models.RosterUnit(
            roster=roster,
            unit=unit,
            count=1,
            extra_weapons_json=json.dumps(
                {
                    "weapons": {
                        str(sword_a.id): 1,
                        str(name_match_a.id): 2,
                        str(unmatched_weapon_a.id): 3,
                        str(custom_weapon.id): 4,
                    }
                },
                ensure_ascii=False,
            ),
        )
        session.add(roster_unit)

        spell = models.ArmySpell(
            army=army,
            kind="weapon",
            weapon=custom_weapon,
            position=1,
            cost=0,
        )
        session.add(spell)
        session.flush()

        request = Request({"type": "http"})
        response = armies_router.update_army(
            army_id=army.id,
            request=request,
            name="Bravo",
            armory_id=str(armory_b.id),
            db=session,
            current_user=user,
        )

        assert response.status_code == 303

        refreshed_army = session.get(models.Army, army.id)
        assert refreshed_army.armory_id == armory_b.id
        assert refreshed_army.name == "Bravo"

        refreshed_custom_weapon = session.get(models.Weapon, custom_weapon.id)
        assert refreshed_custom_weapon.armory_id == armory_b.id

        updated_unit = session.execute(
            select(models.Unit)
            .where(models.Unit.id == unit.id)
            .options(
                selectinload(models.Unit.weapon_links).selectinload(models.UnitWeapon.weapon),
                selectinload(models.Unit.default_weapon),
            )
        ).scalar_one()

        link_weapon_ids = {link.weapon_id for link in updated_unit.weapon_links}
        assert len(link_weapon_ids) == 3
        assert sword_b.id in link_weapon_ids
        assert name_match_b.id in link_weapon_ids
        assert custom_weapon.id in link_weapon_ids
        assert unmatched_weapon_a.id not in link_weapon_ids

        primary_ids = [link.weapon_id for link in updated_unit.weapon_links if link.is_primary]
        assert primary_ids == [sword_b.id]
        assert updated_unit.default_weapon_id == sword_b.id
        assert updated_unit.default_weapon.armory_id == armory_b.id

        updated_roster_unit = session.get(models.RosterUnit, roster_unit.id)
        loadout = json.loads(updated_roster_unit.extra_weapons_json)
        weapons_section = loadout.get("weapons", {})
        assert str(sword_b.id) in weapons_section
        assert weapons_section[str(sword_b.id)] == 1
        assert str(name_match_b.id) in weapons_section
        assert weapons_section[str(name_match_b.id)] == 2
        assert str(unmatched_weapon_a.id) not in weapons_section
        assert str(custom_weapon.id) in weapons_section
        assert weapons_section[str(custom_weapon.id)] == 4

        updated_spell = session.execute(
            select(models.ArmySpell)
            .where(models.ArmySpell.id == spell.id)
            .options(selectinload(models.ArmySpell.weapon))
        ).scalar_one()
        assert updated_spell.weapon_id == custom_weapon.id
        assert updated_spell.weapon.armory_id == armory_b.id
    finally:
        session.close()
