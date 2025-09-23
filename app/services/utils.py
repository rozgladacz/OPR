from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


def split_owned(items: Sequence, user: models.User | None):
    mine = []
    global_items = []
    others = []
    for item in items:
        owner_id = getattr(item, "owner_id", None)
        if user and owner_id == user.id:
            mine.append(item)
        elif owner_id is None:
            global_items.append(item)
        elif user and user.is_admin:
            others.append(item)
    return mine, global_items, others


def parse_flags(text: str | None) -> dict:
    if not text:
        return {}
    entries = [entry.strip() for entry in text.split(",") if entry.strip()]
    result = {}
    for entry in entries:
        if "=" in entry:
            key, value = entry.split("=", 1)
            result[key.strip()] = value.strip()
        else:
            result[entry] = True
    return result


def ensure_armory_variant_sync(db: Session, armory: models.Armory) -> None:
    if armory.parent_id is None:
        return

    if armory.parent is not None:
        ensure_armory_variant_sync(db, armory.parent)

    parent_weapon_ids = {
        weapon_id
        for weapon_id in db.execute(
            select(models.Weapon.id).where(models.Weapon.armory_id == armory.parent_id)
        ).scalars()
    }
    existing_parent_ids = {
        parent_id
        for parent_id in db.execute(
            select(models.Weapon.parent_id).where(
                models.Weapon.armory_id == armory.id,
                models.Weapon.parent_id.is_not(None),
            )
        )
        .scalars()
        .all()
        if parent_id is not None
    }

    missing_ids = parent_weapon_ids - existing_parent_ids
    for parent_weapon_id in missing_ids:
        parent_weapon = db.get(models.Weapon, parent_weapon_id)
        if not parent_weapon:
            continue
        clone = models.Weapon(armory=armory, owner_id=armory.owner_id, parent=parent_weapon)
        db.add(clone)

    variant_weapons = db.execute(
        select(models.Weapon).where(
            models.Weapon.armory_id == armory.id,
            models.Weapon.parent_id.is_not(None),
        )
    ).scalars().all()
    for weapon in variant_weapons:
        if weapon.parent_id is not None and db.get(models.Weapon, weapon.parent_id) is None:
            db.delete(weapon)

    db.flush()
