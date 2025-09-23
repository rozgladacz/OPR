import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DB_URL
from .services import costs

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


def init_db() -> None:
    from sqlalchemy import select

    from . import models
    from .security import hash_password

    db_path = Path(DB_URL.split("///")[-1]) if DB_URL.startswith("sqlite") else None
    first_start = db_path is not None and not db_path.exists()

    Base.metadata.create_all(bind=engine)

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
                    "tags": "Szturmowy, Bez regeneracji, Rozrywający",
                },
                {
                    "name": "Lekki bolter",
                    "range": "18",
                    "attacks": 2,
                    "ap": 1,
                    "tags": "Bez regeneracji, Rozrywający",
                },
                {
                    "name": "Bolter",
                    "range": "24",
                    "attacks": 2,
                    "ap": 1,
                    "tags": "Bez regeneracji, Rozrywający",
                },
                {
                    "name": "Ciężki bolter",
                    "range": "30",
                    "attacks": 4,
                    "ap": 1,
                    "tags": "Bez regeneracji, Rozrywający",
                },
                {
                    "name": "Storm bolter",
                    "range": "18",
                    "attacks": 3,
                    "ap": 1,
                    "tags": "Szturmowy, Bez regeneracji, Rozrywający",
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
                    "tags": "Rozprysk 3, Indirect, Ciężki",
                },
                {
                    "name": "Ręczny miotacz ognia",
                    "range": "",
                    "attacks": 1,
                    "ap": -1,
                    "tags": "Rozprysk 3, Reliable, No cover, No regen",
                },
                {
                    "name": "Lekki miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": -1,
                    "tags": "Rozprysk 3, Reliable, No cover, No regen",
                },
                {
                    "name": "Miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": 0,
                    "tags": "Rozprysk 3, Reliable, No cover, No regen",
                },
                {
                    "name": "Ciężki miotacz ognia",
                    "range": "12",
                    "attacks": 1,
                    "ap": 1,
                    "tags": "Rozprysk 3, Reliable, No cover, No regen",
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
            )
            unit2 = models.Unit(
                name="Szermierz OPR",
                quality=3,
                defense=3,
                toughness=3,
                default_weapon=sword,
                army=army,
                owner_id=None,
            )
            unit1.weapon_links = [models.UnitWeapon(weapon=rifle)]
            unit2.weapon_links = [models.UnitWeapon(weapon=sword)]
            session.add_all([unit1, unit2])

        session.commit()

    if first_start:
        logger.info("Database initialized with sample data at %s", DB_URL)
