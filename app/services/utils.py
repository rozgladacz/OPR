from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..data import abilities as ability_catalog

HIDDEN_TRAIT_SLUGS: set[str] = set()


# Traits with these normalized slugs are part of the internal role handling and
# should never be presented in the UI when editing armies/rosters.  They are
# filtered out anywhere `_is_hidden_trait` is used.
HIDDEN_TRAIT_SLUGS: set[str] = {"wojownik", "strzelec"}


def round_points(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        dec_value = value
    else:
        try:
            dec_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return 0
            dec_value = Decimal(str(numeric))
    return int(dec_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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



def passive_flags_to_payload(text: str | None) -> list[dict]:
    flags = parse_flags(text)
    payload: list[dict] = []
    for slug, value in flags.items():
        raw_slug = str(slug).strip()
        if not raw_slug:
            continue
        is_default = True
        slug_text = raw_slug
        if raw_slug.endswith("?"):
            slug_text = raw_slug[:-1]
            is_default = False
        definition = ability_catalog.find_definition(slug_text)
        payload.append(
            {
                "slug": slug_text,
                "value": None
                if isinstance(value, bool) and value
                else ("" if value is None else str(value)),
                "label": ability_catalog.display_with_value(
                    definition,
                    None
                    if isinstance(value, bool) and value
                    else (None if value is None else str(value)),
                )
                if definition
                else slug_text,
                "description": definition.description if definition else "",
                "is_default": is_default,
            }
        )
    return payload


def passive_payload_to_flags(items: list[dict]) -> str:
    entries: list[str] = []
    for item in items:
        slug = str(item.get("slug", "")).strip()
        if not slug:
            continue
        value = item.get("value")
        is_default = item.get("is_default")
        target_slug = slug
        if isinstance(is_default, bool) and not is_default:
            target_slug = f"{slug}?"
        if value is None or (isinstance(value, str) and not value.strip()):
            entries.append(target_slug)
        else:
            entries.append(f"{target_slug}={value}")
    return ",".join(entries)



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
        clone = models.Weapon(
            armory=armory,
            owner_id=armory.owner_id,
            parent=parent_weapon,
            name=None,
            range=None,
            attacks=None,
            ap=None,
            tags=None,
            notes=None,
        )
        clone.cached_cost = None
        
        db.add(clone)

    variant_weapons = db.execute(
        select(models.Weapon).where(
            models.Weapon.armory_id == armory.id,
            models.Weapon.parent_id.is_not(None),
        )
    ).scalars().all()

    cleaned = False
    for weapon in variant_weapons:
        if weapon.parent_id is not None and db.get(models.Weapon, weapon.parent_id) is None:
            db.delete(weapon)
            cleaned = True
            continue

        if not weapon.parent:
            continue

        parent = weapon.parent

        if weapon.name is not None and weapon.name == parent.effective_name:
            weapon.name = None
            cleaned = True

        if weapon.range is not None and weapon.range == parent.effective_range:
            weapon.range = None
            cleaned = True

        if weapon.attacks is not None and math.isclose(
            float(weapon.attacks),
            parent.effective_attacks,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            weapon.attacks = None
            cleaned = True

        if weapon.ap is not None and weapon.ap == parent.effective_ap:
            weapon.ap = None
            cleaned = True

        parent_tags = parent.effective_tags or ""
        if weapon.tags is not None and (weapon.tags or "") == parent_tags:
            weapon.tags = None
            cleaned = True

        parent_notes = parent.effective_notes or ""
        if weapon.notes is not None and (weapon.notes or "") == parent_notes:
            weapon.notes = None
            cleaned = True

    if cleaned:
        db.flush()