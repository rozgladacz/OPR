import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DB_URL

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

        if not session.execute(select(models.Weapon)).first():
            rifle = models.Weapon(
                name="Karabin",
                range="24",
                attacks=2,
                ap=1,
                tags="Ranged",
                notes="Standardowy karabin piechoty",
                owner_id=None,
            )
            sword = models.Weapon(
                name="Miecz Energetyczny",
                range="Walcz",
                attacks=1,
                ap=2,
                tags="Melee",
                notes="Energia tnąca",
                owner_id=None,
            )
            session.add_all([rifle, sword])

        session.flush()

        if not session.execute(select(models.Army)).first():
            army = models.Army(name="Siewcy Zagłady", ruleset=ruleset, owner_id=None)
            session.add(army)
            session.flush()

            rifle = session.execute(select(models.Weapon).where(models.Weapon.name == "Karabin")).scalar_one()
            sword = session.execute(select(models.Weapon).where(models.Weapon.name == "Miecz Energetyczny")).scalar_one()

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
            session.add_all([unit1, unit2])

        session.commit()

    if first_start:
        logger.info("Database initialized with sample data at %s", DB_URL)
