from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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
        is_mandatory = False
        slug_text = raw_slug
        while slug_text.endswith(("?", "!")):
            if slug_text.endswith("!"):
                slug_text = slug_text[:-1].strip()
                is_mandatory = True
                continue
            if slug_text.endswith("?"):
                slug_text = slug_text[:-1].strip()
                is_default = False
                continue
            break
        slug_text = slug_text.strip()
        if not slug_text:
            continue
        definition = ability_catalog.find_definition(slug_text)
        if isinstance(value, bool) and value:
            value_text = None
        elif value is None:
            value_text = None
        else:
            value_text = str(value)
        payload.append(
            {
                "slug": slug_text,
                "value": value_text if value_text is not None else None,
                "label": ability_catalog.display_with_value(
                    definition,
                    value_text,
                )
                if definition
                else slug_text,
                "description": ability_catalog.combined_description(
                    definition,
                    value_text,
                ),
                "is_default": is_default,
                "is_mandatory": is_mandatory,
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
        is_default_raw = item.get("is_default")
        is_mandatory = bool(item.get("is_mandatory", False))
        if isinstance(is_default_raw, bool):
            is_default = is_default_raw
        else:
            is_default = True
        if is_mandatory:
            is_default = True
        suffix = ""
        if not is_default:
            suffix += "?"
        if is_mandatory:
            suffix += "!"
        target_slug = f"{slug}{suffix}" if suffix else slug
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

    parent_weapons_map: dict[int, models.Weapon] = {}
    if missing_ids:
        parent_weapons = (
            db.execute(
                select(models.Weapon)
                .where(models.Weapon.id.in_(missing_ids))
                .options(selectinload(models.Weapon.parent))
            )
            .scalars()
            .all()
        )
        parent_weapons_map = {weapon.id: weapon for weapon in parent_weapons}

    created_new_clones = False
    for parent_weapon_id in missing_ids:
        parent_weapon = parent_weapons_map.get(parent_weapon_id)
        if not parent_weapon:
            continue
        clone = models.Weapon(
            armory=armory,
            owner_id=armory.owner_id,
            parent=parent_weapon,
            name=None,
            range=None,
            attacks=(
                parent_weapon.attacks
                if parent_weapon.attacks is not None
                else parent_weapon.effective_attacks
            ),
            ap=(
                parent_weapon.ap
                if parent_weapon.ap is not None
                else parent_weapon.effective_ap
            ),
            tags=None,
            notes=None,
        )
        clone.cached_cost = None

        db.add(clone)
        created_new_clones = True

    if created_new_clones:
        db.flush()

    variant_weapons = (
        db.execute(
            select(models.Weapon)
            .where(
                models.Weapon.armory_id == armory.id,
                models.Weapon.parent_id.is_not(None),
            )
            .options(
                selectinload(models.Weapon.parent).selectinload(
                    models.Weapon.parent
                )
            )
        )
        .scalars()
        .all()
    )

    cleaned = False
    for weapon in variant_weapons:
        parent = weapon.parent

        if weapon.parent_id is not None and parent is None:
            db.delete(weapon)
            cleaned = True
            continue

        if not parent:
            continue

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
