from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterator, Sequence, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..data import abilities as ability_catalog

HIDDEN_TRAIT_SLUGS: set[str] = set()


# Traits with these normalized slugs are part of the internal role handling and
# should never be presented in the UI when editing armies/rosters.  They are
# filtered out anywhere `_is_hidden_trait` is used.
HIDDEN_TRAIT_SLUGS: set[str] = {"wojownik", "strzelec"}

ARMY_RULE_OFF_PREFIX = "__army_off__"


class WeaponTreeNode(TypedDict):
    id: int
    name: str
    parent_id: int | None
    parent_name: str | None
    parent_armory_id: int | None
    parent_armory_name: str | None
    has_parent: bool
    has_external_parent: bool
    inherits: bool
    children: list["WeaponTreeNode"]


@dataclass(slots=True)
class ArmoryWeaponCollection:
    items: list[models.Weapon]
    tree: list[WeaponTreeNode]

    def __iter__(self) -> Iterator[models.Weapon]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> models.Weapon:
        return self.items[index]

    @property
    def payload(self) -> list[WeaponTreeNode]:
        return self.tree


def _weapon_sort_key(weapon: models.Weapon) -> tuple[str, int]:
    name = (weapon.effective_name or "").casefold()
    identifier = getattr(weapon, "id", None)
    try:
        numeric_identifier = int(identifier) if identifier is not None else 0
    except (TypeError, ValueError):  # pragma: no cover - defensive
        numeric_identifier = 0
    return name, numeric_identifier


def _build_weapon_tree(
    armory: models.Armory, weapons: list[models.Weapon]
) -> tuple[list[WeaponTreeNode], list[models.Weapon]]:
    weapon_map: dict[int, models.Weapon] = {
        weapon.id: weapon for weapon in weapons if weapon.id is not None
    }
    source_weapon_map: dict[int, models.Weapon] = {}
    children_map: dict[int, list[models.Weapon]] = {}
    roots: list[models.Weapon] = []

    for weapon in weapons:
        parent = weapon.parent
        if (
            parent
            and parent.id is not None
            and getattr(parent, "armory_id", None) != weapon.armory_id
        ):
            visited_sources: set[int] = set()
            current = parent
            while current is not None:
                source_id = getattr(current, "id", None)
                if source_id is None or source_id in visited_sources:
                    break
                visited_sources.add(source_id)
                source_weapon_map.setdefault(source_id, weapon)
                current = getattr(current, "parent", None)

    for weapon in weapons:
        parent_id = weapon.parent_id
        assigned_parent_id: int | None = None
        if parent_id is not None and parent_id in weapon_map:
            assigned_parent_id = parent_id
        else:
            parent = weapon.parent
            if parent is not None and parent_id is not None:
                visited_sources: set[int] = set()
                current = parent
                while current is not None:
                    source_id = getattr(current, "id", None)
                    if source_id is None or source_id in visited_sources:
                        break
                    visited_sources.add(source_id)
                    candidate = source_weapon_map.get(source_id)
                    if candidate is not None and candidate is not weapon:
                        assigned_parent_id = candidate.id
                        break
                    current = getattr(current, "parent", None)
        if assigned_parent_id is not None and assigned_parent_id in weapon_map:
            children_map.setdefault(assigned_parent_id, []).append(weapon)
        else:
            roots.append(weapon)

    ordered_weapons: list[models.Weapon] = []

    def build_nodes(candidates: list[models.Weapon]) -> list[WeaponTreeNode]:
        nodes: list[WeaponTreeNode] = []
        for item in sorted(candidates, key=_weapon_sort_key):
            ordered_weapons.append(item)
            parent = item.parent
            has_parent = item.parent_id is not None
            has_external_parent = bool(
                has_parent and (item.parent_id not in weapon_map)
            )
            parent_name = parent.effective_name if parent else None
            parent_armory_id = parent.armory_id if parent else None
            parent_armory_name = None
            if parent and getattr(parent, "armory", None) is not None:
                parent_armory_name = parent.armory.name
            elif has_external_parent and parent_armory_id == armory.id:
                parent_armory_name = armory.name

            node: WeaponTreeNode = {
                "id": item.id,
                "name": item.effective_name,
                "parent_id": item.parent_id,
                "parent_name": parent_name,
                "parent_armory_id": parent_armory_id,
                "parent_armory_name": parent_armory_name,
                "has_parent": has_parent,
                "has_external_parent": has_external_parent,
                "inherits": item.inherits_from_parent(),
                "children": build_nodes(children_map.get(item.id, [])),
            }
            nodes.append(node)
        return nodes

    tree = build_nodes(roots)

    if len(ordered_weapons) != len(weapons):
        remaining = [weapon for weapon in weapons if weapon not in ordered_weapons]
        for item in sorted(remaining, key=_weapon_sort_key):
            ordered_weapons.append(item)
            parent = item.parent
            has_parent = item.parent_id is not None
            has_external_parent = bool(
                has_parent and (item.parent_id not in weapon_map)
            )
            parent_name = parent.effective_name if parent else None
            parent_armory_id = parent.armory_id if parent else None
            parent_armory_name = None
            if parent and getattr(parent, "armory", None) is not None:
                parent_armory_name = parent.armory.name
            elif has_external_parent and parent_armory_id == armory.id:
                parent_armory_name = armory.name

            tree.append(
                {
                    "id": item.id,
                    "name": item.effective_name,
                    "parent_id": item.parent_id,
                    "parent_name": parent_name,
                    "parent_armory_id": parent_armory_id,
                    "parent_armory_name": parent_armory_name,
                    "has_parent": has_parent,
                    "has_external_parent": has_external_parent,
                    "inherits": item.inherits_from_parent(),
                    "children": [],
                }
            )

    return tree, ordered_weapons


def load_armory_weapons(db: Session, armory: models.Armory) -> ArmoryWeaponCollection:
    ensure_armory_variant_sync(db, armory)

    parent_loader = selectinload(models.Weapon.parent)
    grandparent_loader = selectinload(models.Weapon.parent).selectinload(
        models.Weapon.parent
    )
    parent_armory_loader = selectinload(models.Weapon.parent).selectinload(
        models.Weapon.armory
    )
    grandparent_armory_loader = (
        selectinload(models.Weapon.parent)
        .selectinload(models.Weapon.parent)
        .selectinload(models.Weapon.armory)
    )

    weapons = (
        db.execute(
            select(models.Weapon)
            .where(
                models.Weapon.armory_id == armory.id,
                models.Weapon.army_id.is_(None),
            )
            .options(
                parent_loader,
                grandparent_loader,
                parent_armory_loader,
                grandparent_armory_loader,
            )
        )
        .scalars()
        .all()
    )

    tree, ordered_weapons = _build_weapon_tree(armory, weapons)
    return ArmoryWeaponCollection(items=ordered_weapons, tree=tree)


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


def _strip_army_rule_label(label_hint: str | None) -> str:
    if label_hint is None:
        return ""
    text = str(label_hint).strip()
    if not text:
        return ""
    text = text.strip("-–—: ")
    lowered = text.casefold()
    if lowered.startswith("brak"):
        colon_index = text.find(":")
        if colon_index >= 0:
            text = text[colon_index + 1 :].strip()
        else:
            text = text[4:].strip()
    return text.strip("-–—: ")


def army_rule_base_label(slug: str, label_hint: str | None = None) -> str:
    cleaned_hint = _strip_army_rule_label(label_hint)
    if cleaned_hint:
        return cleaned_hint
    slug_text = str(slug or "").strip()
    if slug_text.startswith(ARMY_RULE_OFF_PREFIX):
        slug_text = slug_text[len(ARMY_RULE_OFF_PREFIX) :]
    fallback = slug_text or "zasada armii"
    normalized = fallback.replace("_", " ").strip()
    return normalized or fallback


def army_rule_disabled_texts(
    slug: str, label_hint: str | None = None
) -> tuple[str, str, str]:
    base_label = army_rule_base_label(slug, label_hint)
    display_label = f"Brak: {base_label}"
    description = f"Wyłącza zasadę armii „{base_label}” dla tej jednostki."
    return base_label, display_label, description


@functools.lru_cache(maxsize=None)
def _cached_passive_payload(text: str | None) -> tuple[tuple[Any, ...], ...]:
    flags = parse_flags(text)
    entries: list[tuple[Any, ...]] = []
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
        label = (
            ability_catalog.display_with_value(
                definition,
                value_text,
            )
            if definition
            else slug_text
        )
        description = ability_catalog.combined_description(
            definition,
            value_text,
        )
        entries.append(
            (
                slug_text,
                value_text if value_text is not None else None,
                label,
                description,
                is_default,
                is_mandatory,
            )
        )
    return tuple(entries)


def passive_flags_to_payload(text: str | None) -> list[dict]:
    cached_payload = _cached_passive_payload(text)
    payload: list[dict] = []
    for slug, value, label, description, is_default, is_mandatory in cached_payload:
        normalized_value = value
        normalized_label = label
        normalized_description = description
        if slug.startswith(ARMY_RULE_OFF_PREFIX):
            base_label, display_label, default_description = army_rule_disabled_texts(
                slug,
                value or label,
            )
            normalized_value = base_label
            normalized_label = display_label
            if not normalized_description:
                normalized_description = default_description
        payload.append(
            {
                "slug": slug,
                "value": normalized_value,
                "label": normalized_label,
                "description": normalized_description,
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

    synced_variants: set[int] = db.info.setdefault("_armory_variant_synced", set())
    if armory.id in synced_variants:
        return

    if armory.parent is not None:
        ensure_armory_variant_sync(db, armory.parent)

    synced_variants.add(armory.id)

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
        parent_cached_cost = parent_weapon.effective_cached_cost
        clone.cached_cost = parent_cached_cost if parent_cached_cost is not None else None

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

    if created_new_clones or cleaned:
        synced_variants.discard(armory.id)
