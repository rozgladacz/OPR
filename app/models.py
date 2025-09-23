from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _format_range(value: str | None) -> str:
    if value is None:
        return "Wręcz"
    raw = str(value).strip()
    if not raw:
        return "Wręcz"
    lowered = raw.lower()
    if lowered in {"0", "melee", "walcz", "walka", "wręcz", "wrecz"}:
        return "Wręcz"
    cleaned = raw.replace('"', "").replace("''", "").strip()
    try:
        number = int(float(cleaned))
    except ValueError:
        return raw
    return f"{number}\""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def touch_timestamps(mapper, connection, target) -> None:  # pragma: no cover - SQLAlchemy hook
    now = datetime.utcnow()
    if getattr(target, "created_at", None) is None:
        target.created_at = now
    target.updated_at = now


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    armies: Mapped[List["Army"]] = relationship(back_populates="owner")
    weapons: Mapped[List["Weapon"]] = relationship(back_populates="owner")
    rosters: Mapped[List["Roster"]] = relationship(back_populates="owner")
    abilities: Mapped[List["Ability"]] = relationship(
        "Ability", back_populates="owner", cascade="all, delete-orphan"
    )


class RuleSet(TimestampMixin, Base):
    __tablename__ = "rulesets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    armies: Mapped[List["Army"]] = relationship(back_populates="ruleset")


class Ability(TimestampMixin, Base):
    __tablename__ = "abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    cost_hint: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    owner: Mapped[Optional[User]] = relationship(back_populates="abilities")
    unit_links: Mapped[List["UnitAbility"]] = relationship(back_populates="ability")
class Weapon(TimestampMixin, Base):
    __tablename__ = "weapons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    range: Mapped[str] = mapped_column(String(50), nullable=False)
    attacks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cached_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("weapons.id"), nullable=True)
    army_id: Mapped[Optional[int]] = mapped_column(ForeignKey("armies.id"), nullable=True)

    owner: Mapped[Optional[User]] = relationship(back_populates="weapons", foreign_keys=[owner_id])
    parent: Mapped[Optional["Weapon"]] = relationship(remote_side="Weapon.id")
    army: Mapped[Optional["Army"]] = relationship(back_populates="weapons")
    units: Mapped[List["Unit"]] = relationship(back_populates="default_weapon")
    roster_units: Mapped[List["RosterUnit"]] = relationship(back_populates="selected_weapon")

    @property
    def display_range(self) -> str:
        return _format_range(self.range)


class Army(TimestampMixin, Base):
    __tablename__ = "armies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("armies.id"), nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"), nullable=False)

    parent: Mapped[Optional["Army"]] = relationship(remote_side="Army.id")
    owner: Mapped[Optional[User]] = relationship(back_populates="armies")
    ruleset: Mapped[RuleSet] = relationship(back_populates="armies")
    units: Mapped[List["Unit"]] = relationship(back_populates="army", cascade="all, delete-orphan")
    weapons: Mapped[List[Weapon]] = relationship(back_populates="army")
    rosters: Mapped[List["Roster"]] = relationship(back_populates="army")


class Unit(TimestampMixin, Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)
    defense: Mapped[int] = mapped_column(Integer, nullable=False)
    toughness: Mapped[int] = mapped_column(Integer, nullable=False)
    flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_weapon_id: Mapped[Optional[int]] = mapped_column(ForeignKey("weapons.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("units.id"), nullable=True)
    army_id: Mapped[int] = mapped_column(ForeignKey("armies.id"), nullable=False)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    army: Mapped[Army] = relationship(back_populates="units")
    owner: Mapped[Optional[User]] = relationship()
    default_weapon: Mapped[Optional[Weapon]] = relationship(back_populates="units", foreign_keys=[default_weapon_id])
    parent: Mapped[Optional["Unit"]] = relationship(remote_side="Unit.id")
    abilities: Mapped[List["UnitAbility"]] = relationship(back_populates="unit", cascade="all, delete-orphan")
    roster_units: Mapped[List["RosterUnit"]] = relationship(back_populates="unit")


class UnitAbility(TimestampMixin, Base):
    __tablename__ = "unit_abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    ability_id: Mapped[int] = mapped_column(ForeignKey("abilities.id"), nullable=False)
    params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    unit: Mapped[Unit] = relationship(back_populates="abilities")
    ability: Mapped[Ability] = relationship(back_populates="unit_links")


class Roster(TimestampMixin, Base):
    __tablename__ = "rosters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    army_id: Mapped[int] = mapped_column(ForeignKey("armies.id"), nullable=False)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    points_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    army: Mapped[Army] = relationship(back_populates="rosters")
    owner: Mapped[Optional[User]] = relationship(back_populates="rosters")
    roster_units: Mapped[List["RosterUnit"]] = relationship(back_populates="roster", cascade="all, delete-orphan")


class RosterUnit(TimestampMixin, Base):
    __tablename__ = "roster_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roster_id: Mapped[int] = mapped_column(ForeignKey("rosters.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    selected_weapon_id: Mapped[Optional[int]] = mapped_column(ForeignKey("weapons.id"), nullable=True)
    extra_weapons_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cached_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    roster: Mapped[Roster] = relationship(back_populates="roster_units")
    unit: Mapped[Unit] = relationship(back_populates="roster_units")
    selected_weapon: Mapped[Optional[Weapon]] = relationship(back_populates="roster_units")


for cls in [User, RuleSet, Ability, Weapon, Army, Unit, UnitAbility, Roster, RosterUnit]:
    event.listen(cls, "before_insert", touch_timestamps)
    event.listen(cls, "before_update", touch_timestamps)
