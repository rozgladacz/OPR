import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DB_URL
from .services import ability_registry, costs

logger = logging.getLogger(__name__)

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_default_armory(connection) -> int:
    result = connection.execute(
        text(
            "SELECT id FROM armories WHERE owner_id IS NULL ORDER BY id LIMIT 1"
        )
    ).scalar_one_or_none()
    if result is not None:
        return result

    now = datetime.utcnow()
    connection.execute(
        text(
            """
            INSERT INTO armories (name, owner_id, parent_id, created_at, updated_at)
            VALUES (:name, NULL, NULL, :created_at, :updated_at)
            """
        ),
        {
            "name": "Domyślna zbrojownia",
            "created_at": now,
            "updated_at": now,
        },
    )
    return connection.execute(
        text(
            "SELECT id FROM armories WHERE owner_id IS NULL ORDER BY id LIMIT 1"
        )
    ).scalar_one()


def _rebuild_weapons_table(connection, default_armory_id: int) -> None:
    from . import models

    logger.info("Migrating weapons table to support armories and inheritance")
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(text("DROP TABLE IF EXISTS weapons_old"))
        connection.execute(text("ALTER TABLE weapons RENAME TO weapons_old"))
        models.Weapon.__table__.create(connection)
        connection.execute(
            text(
                """
                INSERT INTO weapons (
                    id, name, range, attacks, ap, tags, notes, cached_cost,
                    owner_id, parent_id, armory_id, army_id, created_at, updated_at
                )
                SELECT
                    id, name, range, attacks, ap, tags, notes, cached_cost,
                    owner_id, parent_id, :armory_id, army_id, created_at, updated_at
                FROM weapons_old
                """
            ),
            {"armory_id": default_armory_id},
        )
        connection.execute(text("DROP TABLE weapons_old"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _rebuild_armies_table(connection, default_armory_id: int) -> None:
    from . import models

    logger.info("Migrating armies table to link armories")
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(text("DROP TABLE IF EXISTS armies_old"))
        connection.execute(text("ALTER TABLE armies RENAME TO armies_old"))
        models.Army.__table__.create(connection)
        connection.execute(
            text(
                """
                INSERT INTO armies (
                    id, name, parent_id, owner_id, ruleset_id, armory_id, created_at, updated_at
                )
                SELECT
                    id, name, parent_id, owner_id, ruleset_id, :armory_id, created_at, updated_at
                FROM armies_old
                """
            ),
            {"armory_id": default_armory_id},
        )
        connection.execute(text("DROP TABLE armies_old"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _rebuild_unit_weapons_table(connection) -> None:
    from . import models

    logger.info("Migrating unit_weapons table to include default counts and positions")
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(text("DROP TABLE IF EXISTS unit_weapons_old"))
        connection.execute(text("ALTER TABLE unit_weapons RENAME TO unit_weapons_old"))
        models.UnitWeapon.__table__.create(connection)
        connection.execute(
            text(
                """
                INSERT INTO unit_weapons (
                    id, unit_id, weapon_id, is_default, default_count, position, created_at, updated_at
                )
                SELECT id, unit_id, weapon_id, is_default, 1, 0, created_at, updated_at
                FROM unit_weapons_old
                """
            )
        )
        connection.execute(text("DROP TABLE unit_weapons_old"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _initialize_unit_positions(connection) -> None:
    logger.info("Initializing unit positions")
    rows = connection.execute(
        text("SELECT id, army_id FROM units ORDER BY army_id, id")
    ).all()
    offsets: dict[int, int] = {}
    for row in rows:
        mapping = row._mapping
        army_id = mapping["army_id"]
        position = offsets.get(army_id, 0)
        connection.execute(
            text("UPDATE units SET position = :position WHERE id = :id"),
            {"position": position, "id": mapping["id"]},
        )
        offsets[army_id] = position + 1


def _initialize_roster_unit_positions(connection) -> None:
    logger.info("Initializing roster unit positions")
    rows = connection.execute(
        text("SELECT id, roster_id FROM roster_units ORDER BY roster_id, id")
    ).all()
    offsets: dict[int, int] = {}
    for row in rows:
        mapping = row._mapping
        roster_id = mapping["roster_id"]
        position = offsets.get(roster_id, 0)
        connection.execute(
            text("UPDATE roster_units SET position = :position WHERE id = :id"),
            {"position": position, "id": mapping["id"]},
        )
        offsets[roster_id] = position + 1


def _initialize_unit_ability_positions(connection) -> None:
    logger.info("Initializing unit ability positions")
    rows = connection.execute(
        text("SELECT id, unit_id FROM unit_abilities ORDER BY unit_id, id")
    ).all()
    offsets: dict[int, int] = {}
    for row in rows:
        mapping = row._mapping
        unit_id = mapping["unit_id"]
        position = offsets.get(unit_id, 0)
        connection.execute(
            text("UPDATE unit_abilities SET position = :position WHERE id = :id"),
            {"position": position, "id": mapping["id"]},
        )
        offsets[unit_id] = position + 1


def _normalize_roster_unit_loadouts(connection) -> None:
    logger.info("Normalizing roster unit loadouts before removing selected_weapon_id")
    rows = connection.execute(
        text(
            """
            SELECT id, extra_weapons_json, selected_weapon_id
            FROM roster_units
            WHERE selected_weapon_id IS NOT NULL
            """
        )
    ).mappings()
    for row in rows:
        weapon_id = row["selected_weapon_id"]
        if weapon_id is None:
            continue
        payload_text = row["extra_weapons_json"]
        if payload_text:
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        weapons = payload.get("weapons")
        if not isinstance(weapons, dict):
            weapons = {}
        key = str(weapon_id)
        if key not in weapons:
            weapons[key] = 1
        payload["weapons"] = weapons
        payload.setdefault("active", {})
        payload.setdefault("aura", {})
        payload.setdefault("passive", {})
        payload.setdefault("active_labels", {})
        payload.setdefault("aura_labels", {})
        connection.execute(
            text(
                "UPDATE roster_units SET extra_weapons_json = :payload WHERE id = :id"
            ),
            {"payload": json.dumps(payload, ensure_ascii=False), "id": row["id"]},
        )


def _rebuild_roster_units_table(connection) -> None:
    from . import models

    logger.info("Rebuilding roster_units table without selected_weapon_id column")
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(text("DROP TABLE IF EXISTS roster_units_old"))
        connection.execute(text("ALTER TABLE roster_units RENAME TO roster_units_old"))
        models.RosterUnit.__table__.create(connection)
        connection.execute(
            text(
                """
                INSERT INTO roster_units (
                    id, roster_id, unit_id, count, extra_weapons_json,
                    cached_cost, custom_name, position, created_at, updated_at
                )
                SELECT
                    id, roster_id, unit_id, count, extra_weapons_json,
                    cached_cost, custom_name, position, created_at, updated_at
                FROM roster_units_old
                """
            )
        )
        connection.execute(text("DROP TABLE roster_units_old"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_schema() -> None:
    from sqlalchemy import inspect

    if not DB_URL.startswith("sqlite"):
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "armories" not in table_names:
            return

        default_armory_id = _ensure_default_armory(connection)

        if "weapons" in table_names:
            columns = inspector.get_columns("weapons")
            column_names = {column["name"] for column in columns}
            requires_armory_column = "armory_id" not in column_names
            inheritance_columns = {"name", "range", "attacks", "ap"}
            requires_nullable_update = any(
                column["name"] in inheritance_columns and not column["nullable"]
                for column in columns
            )
            if requires_armory_column or requires_nullable_update:
                _rebuild_weapons_table(connection, default_armory_id)

        if "armies" in table_names:
            columns = inspector.get_columns("armies")
            if "armory_id" not in {column["name"] for column in columns}:
                _rebuild_armies_table(connection, default_armory_id)

        if "unit_weapons" in table_names:
            columns = inspector.get_columns("unit_weapons")
            column_names = {column["name"] for column in columns}
            if not {"default_count", "position"}.issubset(column_names):
                _rebuild_unit_weapons_table(connection)

        if "units" in table_names:
            columns = inspector.get_columns("units")
            column_names = {column["name"] for column in columns}
            if "position" not in column_names:
                logger.info("Adding position column to units table")
                connection.execute(
                    text(
                        "ALTER TABLE units ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
                    )
                )
                _initialize_unit_positions(connection)
            if "typical_models" not in column_names:
                logger.info("Adding typical_models column to units table")
                connection.execute(
                    text(
                        "ALTER TABLE units ADD COLUMN typical_models INTEGER NOT NULL DEFAULT 1"
                    )
                )

        if "roster_units" in table_names:
            columns = inspector.get_columns("roster_units")
            column_names = {column["name"] for column in columns}
            if "selected_weapon_id" in column_names:
                _normalize_roster_unit_loadouts(connection)
                _rebuild_roster_units_table(connection)
                columns = inspector.get_columns("roster_units")
                column_names = {column["name"] for column in columns}
            if "custom_name" not in column_names:
                logger.info("Adding custom_name column to roster_units table")
                connection.execute(
                    text("ALTER TABLE roster_units ADD COLUMN custom_name VARCHAR(120)")
                )
            if "position" not in column_names:
                logger.info("Adding position column to roster_units table")
                connection.execute(
                    text(
                        "ALTER TABLE roster_units ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
                    )
                )
                _initialize_roster_unit_positions(connection)

        if "unit_abilities" in table_names:
            columns = inspector.get_columns("unit_abilities")
            column_names = {column["name"] for column in columns}
            if "position" not in column_names:
                logger.info("Adding position column to unit_abilities table")
                connection.execute(
                    text(
                        "ALTER TABLE unit_abilities ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
                    )
                )
                _initialize_unit_ability_positions(connection)



def init_db() -> None:
    from sqlalchemy import select, update

    from . import models
    from .security import hash_password

    db_path = Path(DB_URL.split("///")[-1]) if DB_URL.startswith("sqlite") else None
    first_start = db_path is not None and not db_path.exists()

    Base.metadata.create_all(bind=engine)
    _migrate_schema()

    with SessionLocal() as session:
        admin = session.execute(select(models.User).where(models.User.username == "admin")).scalar_one_or_none()
        if admin is None:
            admin = models.User(
                username="admin",
                password_hash=hash_password("admin"),
                is_admin=True,
            )
            session.add(admin)
            logger.warning("Default admin user created with username 'admin' and password 'admin'. Please change it.")

        ruleset = session.execute(select(models.RuleSet).where(models.RuleSet.name == "Default")).scalar_one_or_none()
        if ruleset is None:
            ruleset = models.RuleSet(name="Default")
            session.add(ruleset)

        session.flush()

        default_armory = (
            session.execute(
                select(models.Armory)
                .where(models.Armory.owner_id.is_(None))
                .order_by(models.Armory.id)
            )
            .scalars()
            .first()
        )
        if default_armory is None:
            default_armory = models.Armory(name="Domyślna zbrojownia", owner_id=None)
            session.add(default_armory)
            session.flush()


        ability_registry.sync_definitions(session)
        
        if not session.execute(select(models.Weapon)).first():
            weapon_specs = [
                {"name": "Lekka broń ręczna", "range": "", "attacks": 1, "ap": -1, "tags": ""},
                {"name": "Broń ręczna", "range": "", "attacks": 1, "ap": 0, "tags": ""},
                {"name": "Piłomiecz", "range": "", "attacks": 2, "ap": 0, "tags": ""},
                {"name": "Eviscertaor", "range": "", "attacks": 3, "ap": 0, "tags": "Impet"},
                {"name": "Miecz energetyczny", "range": "", "attacks": 2, "ap": 2, "tags": ""},
                {"name": "Rękawica energetyczna", "range": "", "attacks": 1, "ap": 2, "tags": "Deadly 3"},
                {
                    "name": "Piłorękawica",
                    "range": "",
                    "attacks": 1,
                    "ap": 3,
                    "tags": "Deadly 3, Rozrywająca",
                },
                {"name": "Ogryn-pałka", "range": "", "attacks": 3, "ap": 1, "tags": ""},
                {"name": "Młot energetyczny", "range": "", "attacks": 1, "ap": 1, "tags": "Rozprysk 3"},
                {"name": "Włócznia", "range": "", "attacks": 1, "ap": 0, "tags": "Impet"},
                {"name": "Laspistol", "range": "12", "attacks": 1, "ap": 0, "tags": "Szturmowy"},
                {"name": "Lasgun", "range": "24", "attacks": 1, "ap": 0, "tags": ""},
                {"name": "Hellgun", "range": "24", "attacks": 1, "ap": 1, "tags": ""},
                {"name": "Vollyegun", "range": "18", "attacks": 3, "ap": 1, "tags": ""},
                {"name": "Lascanon", "range": "30", "attacks": 1, "ap": 2, "tags": "Deadly 3"},
                {"name": "Multilaser", "range": "24", "attacks": 3, "ap": 1, "tags": ""},
                {"name": "Meltagun", "range": "12", "attacks": 1, "ap": 3, "tags": "Deadly 3"},
                {
                    "name": "Bolt pistol",
                    "range": "12",
                    "attacks": 2,
                    "ap": 1,
                    "tags": "Szturmowy, Brutalny, Rozrywający",
                },
                {
                    "name": "Lekki bolter",
                    "range": "18",
                    "attacks": 2,
                    "ap": 1,
                    "tags": "Brutalny, Rozrywający",
                },
                {
                    "name": "Bolter",
                    "range": "24",
                    "attacks": 2,
                    "ap": 1,
                    "tags": "Brutalny, Rozrywający",
                },
                {
                    "name": "Ciężki bolter",
                    "range": "30",
                    "attacks": 4,
                    "ap": 1,
                    "tags": "Brutalny, Rozrywający",
                },
                {
                    "name": "Storm bolter",
                    "range": "18",
                    "attacks": 3,
                    "ap": 1,
                    "tags": "Szturmowy, Brutalny, Rozrywający",
                },
                {
                    "name": "Pistolet plazmowy",
                    "range": "12",
                    "attacks": 1,
                    "ap": 3,
                    "tags": "Szturmowy, Overcharge",
                },
                {
                    "name": "Lekki karabin plazmowy",
                    "range": "18",
                    "attacks": 1,
                    "ap": 3,
                    "tags": "Overcharge",
                },
                {
                    "name": "Karbin plazmowy",
                    "range": "24",
                    "attacks": 1,
                    "ap": 3,
                    "tags": "Overcharge",
                },
                {
                    "name": "Działo plazmowe",
                    "range": "30",
                    "attacks": 1,
                    "ap": 3,
                    "tags": "Overcharge, Rozprysk 3",
                },
                {"name": "Lekki granatnik", "range": "18", "attacks": 1, "ap": -1, "tags": "Rozprysk 3"},
                {"name": "Granatnik", "range": "24", "attacks": 1, "ap": -1, "tags": "Rozprysk 3"},
                {
                    "name": "Moździerz",
                    "range": "30",
                    "attacks": 1,
                    "ap": 0,
                    "tags": "Rozprysk 3, Indirect",
                },
                {
                    "name": "Ręczny miotacz ognia",
                    "range": "",
                    "attacks": 1,
                    "ap": -1,
                    "tags": "Rozprysk 3, Reliable, No cover, Brutal",
                },
                {
                    "name": "Lekki miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": -1,
                    "tags": "Rozprysk 3, Reliable, No cover, Brutal",
                },
                {
                    "name": "Miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": 0,
                    "tags": "Rozprysk 3, Reliable, No cover, Brutal",
                },
                {
                    "name": "Ciężki miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": 1,
                    "tags": "Rozprysk 3, Reliable, No cover, Brutal",
                },
                {"name": "Strzelba", "range": "12", "attacks": 2, "ap": -1, "tags": "Szturmowa"},
                {"name": "Snajperka", "range": "30", "attacks": 1, "ap": 1, "tags": "Precyzyjna, Niezawodna"},
                {"name": "Taranowanie", "range": "", "attacks": 1, "ap": -1, "tags": "Impet"},
            ]

            weapons: list[models.Weapon] = []
            for spec in weapon_specs:
                weapon = models.Weapon(
                    name=spec["name"],
                    range=spec["range"],
                    attacks=spec["attacks"],
                    ap=spec["ap"],
                    tags=spec.get("tags") or None,
                    owner_id=default_armory.owner_id,
                    armory=default_armory,
                )
                weapon.cached_cost = costs.weapon_cost(weapon)
                weapons.append(weapon)

            session.add_all(weapons)

        session.execute(
            update(models.Weapon)
            .where(models.Weapon.armory_id.is_(None))
            .values(armory_id=default_armory.id)
        )
        session.execute(
            update(models.Army)
            .where(models.Army.armory_id.is_(None))
            .values(armory_id=default_armory.id)
        )

        session.flush()

        if not session.execute(select(models.Army)).first():
            army = models.Army(
                name="Siewcy Zagłady",
                ruleset=ruleset,
                owner_id=None,
                armory=default_armory,
            )
            session.add(army)
            session.flush()

            rifle = session.execute(select(models.Weapon).where(models.Weapon.name == "Lasgun")).scalar_one()
            sword = session.execute(select(models.Weapon).where(models.Weapon.name == "Miecz energetyczny")).scalar_one()

            unit1 = models.Unit(
                name="Piechur OPR",
                quality=4,
                defense=4,
                toughness=3,
                default_weapon=rifle,
                army=army,
                owner_id=None,
                typical_models=1,
            )
            unit2 = models.Unit(
                name="Szermierz OPR",
                quality=3,
                defense=3,
                toughness=3,
                default_weapon=sword,
                army=army,
                owner_id=None,
                typical_models=1,
            )
            unit1.weapon_links = [models.UnitWeapon(weapon=rifle, position=0)]
            unit2.weapon_links = [models.UnitWeapon(weapon=sword, position=0)]
            session.add_all([unit1, unit2])

        session.commit()

    if first_start:
        logger.info("Database initialized with sample data at %s", DB_URL)
