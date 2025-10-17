from __future__ import annotations

import math
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


ARMY_SPELL_NAME_MAX_LENGTH = 60


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
    armories: Mapped[List["Armory"]] = relationship(back_populates="owner")
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


class Armory(TimestampMixin, Base):
    __tablename__ = "armories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("armories.id"), nullable=True)

    owner: Mapped[Optional[User]] = relationship(back_populates="armories")
    parent: Mapped[Optional["Armory"]] = relationship(remote_side="Armory.id", back_populates="variants")
    variants: Mapped[List["Armory"]] = relationship(back_populates="parent")
    weapons: Mapped[List["Weapon"]] = relationship(
        back_populates="armory", cascade="all, delete-orphan"
    )
    armies: Mapped[List["Army"]] = relationship(back_populates="armory")


class Weapon(TimestampMixin, Base):
    __tablename__ = "weapons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    attacks: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=1.0)
    ap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    tags: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cached_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("weapons.id"), nullable=True)
    armory_id: Mapped[int] = mapped_column(ForeignKey("armories.id"), nullable=False)
    army_id: Mapped[Optional[int]] = mapped_column(ForeignKey("armies.id"), nullable=True)

    owner: Mapped[Optional[User]] = relationship(back_populates="weapons", foreign_keys=[owner_id])
    parent: Mapped[Optional["Weapon"]] = relationship(remote_side="Weapon.id")
    armory: Mapped[Armory] = relationship(back_populates="weapons")
    army: Mapped[Optional["Army"]] = relationship(back_populates="weapons")
    units: Mapped[List["Unit"]] = relationship(back_populates="default_weapon")

    def _inherited_value(self, attr: str, default=None):
        current: Weapon | None = self
        visited: set[int] = set()
        while current is not None:
            identifier = getattr(current, "id", None)
            if identifier is not None:
                if identifier in visited:
                    break
                visited.add(identifier)
            value = getattr(current, attr)
            if value is not None:
                return value
            current = current.parent
        return default

    def inherits_from_parent(self) -> bool:
        return self.parent_id is not None

    def is_overriding(self, attr: str) -> bool:
        if not self.parent:
            return True
        value = getattr(self, attr)
        if value is None:
            return False
        parent_value = self.parent._inherited_value(attr)
        return value != parent_value

    @property
    def effective_name(self) -> str:
        value = self._inherited_value("name", "")
        return value or ""

    @property
    def effective_range(self) -> str:
        value = self._inherited_value("range", "")
        return value or ""

    @property
    def effective_attacks(self) -> float:
        value = self._inherited_value("attacks", 1.0)
        return float(value if value is not None else 1.0)

    @property

    def display_attacks(self) -> int:
        value = self.effective_attacks
        if not math.isfinite(value):
            return 0
        return int(math.floor(value + 0.5))

    @property

    def effective_ap(self) -> int:
        value = self._inherited_value("ap", 0)
        return int(value if value is not None else 0)

    @property
    def effective_tags(self) -> Optional[str]:
        return self._inherited_value("tags")

    @property
    def effective_notes(self) -> Optional[str]:
        return self._inherited_value("notes")

    @property
    def effective_cached_cost(self) -> Optional[float]:
        value = self._inherited_value("cached_cost")
        return float(value) if value is not None else None

    def has_overrides(self) -> bool:
        if not self.parent:
            return True
        for attr in ("name", "range", "attacks", "ap", "tags", "notes"):
            if getattr(self, attr) is not None:
                return True
        return False


class Army(TimestampMixin, Base):
    __tablename__ = "armies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("armies.id"), nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id"), nullable=False)
    armory_id: Mapped[int] = mapped_column(ForeignKey("armories.id"), nullable=False)

    parent: Mapped[Optional["Army"]] = relationship(remote_side="Army.id")
    owner: Mapped[Optional[User]] = relationship(back_populates="armies")
    ruleset: Mapped[RuleSet] = relationship(back_populates="armies")
    armory: Mapped[Armory] = relationship(back_populates="armies")
    units: Mapped[List["Unit"]] = relationship(
        back_populates="army",
        cascade="all, delete-orphan",
        order_by="Unit.position",
    )
    weapons: Mapped[List[Weapon]] = relationship(back_populates="army")
    rosters: Mapped[List["Roster"]] = relationship(back_populates="army")
    spells: Mapped[List["ArmySpell"]] = relationship(
        back_populates="army",
        cascade="all, delete-orphan",
        order_by="ArmySpell.position",
    )


class ArmySpell(TimestampMixin, Base):
    __tablename__ = "army_spells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    army_id: Mapped[int] = mapped_column(ForeignKey("armies.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    ability_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("abilities.id"), nullable=True
    )
    ability_value: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    weapon_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("weapons.id"), nullable=True
    )
    base_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    custom_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    army: Mapped[Army] = relationship(back_populates="spells")
    ability: Mapped[Optional[Ability]] = relationship()
    weapon: Mapped[Optional[Weapon]] = relationship()

    @property
    def normalized_custom_name(self) -> str:
        value = (self.custom_name or "").strip()
        return value[:ARMY_SPELL_NAME_MAX_LENGTH]

    @property
    def base_display_label(self) -> str:
        return (self.base_label or "").strip()

    @property
    def display_label(self) -> str:
        base = self.base_display_label
        custom = self.normalized_custom_name
        if custom and base:
            return f"{custom} [{base}]"
        if custom:
            return custom
        return base

    @property
    def export_label(self) -> str:
        base = self.base_display_label
        custom = self.normalized_custom_name
        if custom and base:
            return f'"{custom}" {base}'
        if custom:
            return f'"{custom}"'
        return base

    @property
    def export_payload(self) -> dict[str, object]:
        return {
            "cost": int(self.cost or 0),
            "label": self.export_label,
            "description": (self.description or "").strip(),
        }


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
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    typical_models: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    army: Mapped[Army] = relationship(back_populates="units")
    owner: Mapped[Optional[User]] = relationship()
    default_weapon: Mapped[Optional[Weapon]] = relationship(back_populates="units", foreign_keys=[default_weapon_id])
    weapon_links: Mapped[List["UnitWeapon"]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by=lambda: (UnitWeapon.position, UnitWeapon.id),
    )
    parent: Mapped[Optional["Unit"]] = relationship(remote_side="Unit.id")
    abilities: Mapped[List["UnitAbility"]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        order_by=lambda: (UnitAbility.position, UnitAbility.id),
    )
    roster_units: Mapped[List["RosterUnit"]] = relationship(back_populates="unit")

    @property
    def typical_model_count(self) -> int:
        try:
            value = int(getattr(self, "typical_models", 1))
        except (TypeError, ValueError):
            value = 1
        if value < 1:
            value = 1
        return value

    @property
    def default_weapons(self) -> List[Weapon]:
        weapons: list[Weapon] = []
        added = False
        for link in getattr(self, "weapon_links", []):
            if link.weapon is None:
                continue
            is_default = bool(getattr(link, "is_default", False))
            count_raw = getattr(link, "default_count", None)
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                count = 1 if is_default else 0
            if count < 0:
                count = 0
            if not is_default and count > 0:
                is_default = True
            if not is_default or count <= 0:
                continue
            weapons.extend([link.weapon] * count)
            added = True
        if not added and self.default_weapon:
            weapons.append(self.default_weapon)
        return weapons

    @property
    def default_weapon_ids(self) -> List[int]:
        ids: list[int] = []
        seen: set[int] = set()
        for link in getattr(self, "weapon_links", []):
            is_default = bool(getattr(link, "is_default", False))
            count_raw = getattr(link, "default_count", None)
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                count = 1 if is_default else 0
            if count < 0:
                count = 0
            if not is_default and count > 0:
                is_default = True
            if not is_default or count <= 0 or link.weapon_id is None:
                continue
            if link.weapon_id not in seen:
                ids.append(link.weapon_id)
                seen.add(link.weapon_id)
        if self.default_weapon_id and self.default_weapon_id not in seen:
            ids.append(self.default_weapon_id)
        return ids

    @property
    def default_weapon_loadout(self) -> List[tuple[Weapon, int]]:
        loadout: list[tuple[Weapon, int]] = []
        for link in getattr(self, "weapon_links", []):
            if link.weapon is None:
                continue
            is_default = bool(getattr(link, "is_default", False))
            count_raw = getattr(link, "default_count", None)
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                count = 1 if is_default else 0
            if count < 0:
                count = 0
            if not is_default and count > 0:
                is_default = True
            if not is_default or count <= 0:
                continue
            loadout.append((link.weapon, count))
        if not loadout and self.default_weapon:
            loadout.append((self.default_weapon, 1))
        return loadout


class UnitWeapon(TimestampMixin, Base):
    __tablename__ = "unit_weapons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    weapon_id: Mapped[int] = mapped_column(ForeignKey("weapons.id"), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    unit: Mapped[Unit] = relationship(back_populates="weapon_links")
    weapon: Mapped[Weapon] = relationship()


class UnitAbility(TimestampMixin, Base):
    __tablename__ = "unit_abilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    ability_id: Mapped[int] = mapped_column(ForeignKey("abilities.id"), nullable=False)
    params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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
    roster_units: Mapped[List["RosterUnit"]] = relationship(
        back_populates="roster",
        cascade="all, delete-orphan",
        order_by="RosterUnit.position",
    )


class RosterUnit(TimestampMixin, Base):
    __tablename__ = "roster_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roster_id: Mapped[int] = mapped_column(ForeignKey("rosters.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    extra_weapons_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cached_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    roster: Mapped[Roster] = relationship(back_populates="roster_units")
    unit: Mapped[Unit] = relationship(back_populates="roster_units")


for cls in [
    User,
    RuleSet,
    Ability,
    Armory,
    Weapon,
    Army,
    Unit,
    UnitWeapon,
    UnitAbility,
    Roster,
    RosterUnit,
    ArmySpell,
]:
    event.listen(cls, "before_insert", touch_timestamps)
    event.listen(cls, "before_update", touch_timestamps)
