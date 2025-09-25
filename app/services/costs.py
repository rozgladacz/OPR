"""Kalkulator kosztów jednostek zgodny z arkuszem VBA."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from .. import models
from ..data import abilities as ability_catalog
from .utils import parse_flags


QUALITY_TABLE = {
    2: {1: 1.2, 2: 1.25},
    3: {1: 1.1, 2: 1.2},
    4: {1: 1.0, 2: 1.15},
    5: {1: 0.9, 2: 1.1},
    6: {1: 0.8, 2: 1.05},
}

DEFENSE_TABLE = {
    1: {2: 2.0, 3: 1.67, 4: 1.33, 5: 1.0, 6: 0.8},
    2: {2: 1.95, 3: 1.6, 4: 1.2, 5: 0.9, 6: 0.67},
    3: {2: 2.05, 3: 1.8, 4: 1.5, 5: 1.3, 6: 1.2},
    4: {2: 3.0, 3: 2.3, 4: 1.8, 5: 1.4, 6: 1.2},
}

TOUGHNESS_SPECIAL = {1: 1.0, 2: 2.15, 3: 3.5}

QUALITY_ROW_ABILITIES = {"nieustraszony", "stracency"}

DEFENSE_ROW_ABILITIES = {
    2: {"delikatny"},
    3: {"niewrazliwy"},
    4: {"regeneracja"},
}

RANGE_TABLE = {0: 0.6, 12: 0.65, 18: 1.0, 24: 1.25, 30: 1.45, 36: 1.55}

AP_BASE = {-1: 0.8, 0: 1.0, 1: 1.5, 2: 1.9, 3: 2.25, 4: 2.5, 5: 2.65}
AP_LANCE = {-1: 0.15, 0: 0.35, 1: 0.3, 2: 0.25, 3: 0.15, 4: 0.1, 5: 0.05}
AP_NO_COVER = {-1: 0.1, 0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05}
AP_CORROSIVE = {-1: 0.05, 0: 0.05, 1: 0.1, 2: 0.25, 3: 0.4, 4: 0.5, 5: 0.55}

BLAST_MULTIPLIER = {2: 1.95, 3: 2.8, 6: 4.3}
DEADLY_MULTIPLIER = {2: 1.9, 3: 2.6, 6: 3.8}

TRANSPORT_MULTIPLIERS = [
    ({"samolot"}, 3.5),
    ({"zasadzka", "zwiadowca"}, 2.5),
    ({"latajacy"}, 1.5),
    ({"szybki", "zwinny"}, 1.25),
]

BASE_COST_FACTOR = 5.0

_RULESET_FALLBACK_PATH = (
    Path(__file__).resolve().parent.parent / "rulesets" / "default.json"
)


@lru_cache()
def default_ruleset_config() -> dict[str, Any]:
    try:
        with _RULESET_FALLBACK_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _apply_ruleset_overrides() -> None:
    config = default_ruleset_config()
    range_modifiers = config.get("range_modifiers")
    if isinstance(range_modifiers, dict):
        for key, value in range_modifiers.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            key_text = str(key).strip().casefold()
            if key_text in {"melee", "m"}:
                RANGE_TABLE[0] = numeric
            else:
                try:
                    RANGE_TABLE[int(key)] = numeric
                except (TypeError, ValueError):
                    continue
    base_factor = config.get("base_cost_factor")
    if isinstance(base_factor, (int, float)) and base_factor > 0:
        global BASE_COST_FACTOR
        BASE_COST_FACTOR = float(base_factor)


_apply_ruleset_overrides()


def normalize_name(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("-", " ").replace("_", " ")
    value = re.sub(r"\s+", " ", value.strip())
    return value.casefold()


def extract_number(text: str | None) -> float:
    if not text:
        return 0.0
    match = re.search(r"[0-9]+(?:[.,][0-9]+)?", str(text))
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))


def flags_to_ability_list(flags: dict | None) -> list[str]:
    abilities: list[str] = []
    for key, value in (flags or {}).items():
        if key is None:
            continue
        name = str(key).strip()
        if not name:
            continue
        if name.endswith("?"):
            name = name[:-1]
        slug = ability_catalog.slug_for_name(name) or name
        if isinstance(value, bool):
            if value:
                abilities.append(slug)
            continue
        if value is None:
            abilities.append(slug)
            continue
        value_str = str(value).strip()
        if not value_str or value_str.casefold() in {"true", "yes"}:
            abilities.append(slug)
        else:
            abilities.append(f"{slug}({value_str})")
    return abilities


def split_traits(text: str | None) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;]", text) if part.strip()]


def clamp_quality(value: int) -> int:
    return max(2, min(6, int(value)))


def clamp_defense(value: int) -> int:
    return max(2, min(6, int(value)))


def quality_modifier(quality: int, row: int) -> float:
    quality = clamp_quality(quality)
    row = 2 if row == 2 else 1
    return QUALITY_TABLE[quality][row]


def defense_modifier(defense: int, row: int) -> float:
    defense = clamp_defense(defense)
    row_dict = DEFENSE_TABLE.get(row, DEFENSE_TABLE[1])
    return row_dict[defense]


def toughness_modifier(toughness: int) -> float:
    toughness = max(int(toughness), 1)
    if toughness in TOUGHNESS_SPECIAL:
        return TOUGHNESS_SPECIAL[toughness]
    return max(1.0, (5 * toughness) // 3 - 2)


def lookup_with_nearest(table: dict[int, float], key: int) -> float:
    if key in table:
        return table[key]
    nearest = min(table, key=lambda existing: abs(existing - key))
    return table[nearest]


def range_multiplier(range_value: int) -> float:
    if range_value in RANGE_TABLE:
        return RANGE_TABLE[range_value]
    nearest = min(RANGE_TABLE, key=lambda existing: abs(existing - range_value))
    return RANGE_TABLE[nearest]


def normalize_range_value(value: str | int | float | None) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        text = str(value).strip()
        if not text:
            return 0
        lowered = text.casefold()
        if lowered in {"melee", "m"}:
            return 0
        numeric = extract_number(lowered)
    if numeric <= 0:
        return 0
    return int(round(numeric))


def ability_identifier(text: str | None) -> str:
    if text is None:
        return ""
    raw = str(text).strip()
    if not raw:
        return ""
    base = raw
    for separator in ("(", "=", ":"):
        if separator in base:
            base = base.split(separator, 1)[0].strip()
    slug = ability_catalog.slug_for_name(base)
    if slug:
        return slug
    return normalize_name(base)


def passive_cost(ability_name: str, tou: float = 1.0, aura: bool = False) -> float:
    slug = ability_identifier(ability_name)
    norm = normalize_name(ability_name)
    key = slug or norm
    if not key:
        return 0.0

    tou = float(tou)

    if slug == "zasadzka":
        return 2.0 * tou
    if slug == "zwiadowca":
        return 2.0 * tou
    if slug == "szybki":
        return 1.0 * tou
    if slug == "wolny":
        return -1.0 * tou
    if slug == "harcownik":
        return 1.5 * tou
    if slug == "nieruchomy":
        return 2.5 * tou
    if slug == "zwinny":
        return 0.5 * tou
    if slug == "niezgrabny":
        return -0.5 * tou
    if slug == "latajacy":
        return 1.0 * tou
    if slug == "samolot":
        return 3.0 * tou
    if slug == "kontra":
        return 2.0 * tou
    if slug == "maskowanie":
        return 2.0 * tou
    if slug == "okopany":
        return 1.0 * tou
    if slug == "tarcza":
        return 1.25 * tou
    if slug == "straznik":
        return 3.0 * tou

    if aura:
        if slug in {"nieustraszony", "stracency"}:
            return 1.5 * tou
        if slug == "delikatny":
            return 0.5 * tou
        if slug == "niewrazliwy":
            return 2.0 * tou
        if slug == "regeneracja":
            return 3.5 * tou
        if slug == "furia":
            return 3.0 * tou
        if slug == "nieustepliwy":
            return 3.5 * tou

    if slug == "strach":
        value = extract_number(ability_name)
        return 0.75 * value

    return 0.0


def _parse_aura_value(name: str, value: str | None) -> tuple[str, float]:
    aura_range = 6.0
    ability_ref = ""
    if value:
        parts = value.split("|", 1)
        if len(parts) == 2:
            ability_ref = parts[0].strip()
            aura_range = extract_number(parts[1]) or 6.0
        else:
            ability_ref = value.strip()
    if not ability_ref:
        desc = normalize_name(name)
        if desc.startswith("aura("):
            match = re.match(r"aura\(([^)]+)\)\s*[:\-–]?\s*(.*)", desc)
            if match:
                aura_range = extract_number(match.group(1)) or 6.0
                raw_ref = match.group(2)
                ability_ref = raw_ref.lstrip(": -–").strip().rstrip(") ")
                ability_ref = ability_ref.strip()
        elif desc.startswith("aura:" ):
            ability_ref = desc.split(":", 1)[1].strip()
        else:
            ability_ref = desc[4:].lstrip(": -–").strip()
    slug = ability_catalog.slug_for_name(ability_ref) or ability_identifier(ability_ref)
    return slug, aura_range


def ability_cost_from_name(
    name: str,
    value: str | None = None,
    unit_abilities: Sequence[str] | None = None,
) -> float:
    desc = normalize_name(name)
    if not desc:
        return 0.0

    ability_set: set[str] = set()
    for item in unit_abilities or []:
        identifier = ability_identifier(item)
        if identifier:
            ability_set.add(identifier)

    if desc.startswith("transport"):
        capacity = extract_number(value or name)
        multiplier = 1.0
        for options, value in TRANSPORT_MULTIPLIERS:
            if ability_set & options:
                multiplier = value
        return capacity * multiplier

    if desc.startswith("aura"):
        ability_slug, aura_range = _parse_aura_value(name, value)
        cost = passive_cost(ability_slug, 8.0, True)
        if abs(aura_range - 12.0) < 1e-6:
            cost *= 2.0
        return cost

    if desc.startswith("mag"):
        return 8.0 * extract_number(value or name)

    if desc == "przekaznik":
        return 4.0

    if desc == "latanie":
        return 20.0

    if desc.startswith("rozkaz"):
        ability_ref = value or (desc.split(":", 1)[1].strip() if ":" in desc else "")
        ability_slug = ability_catalog.slug_for_name(ability_ref) or ability_identifier(ability_ref)
        return passive_cost(ability_slug, 10.0, True)

    if desc == "radio":
        return 3.0

    return 0.0


def base_model_cost(
    quality: int,
    defense: int,
    toughness: int,
    abilities: Sequence[str] | None,
) -> float:
    ability_list = list(abilities or [])
    qua_row = 1
    def_row = 1
    passive_total = 0.0

    for ability in ability_list:
        slug = ability_identifier(ability)
        norm = slug or normalize_name(ability)
        if not norm:
            continue
        if slug in QUALITY_ROW_ABILITIES:
            qua_row = 2
            continue
        matched_def_row = next(
            (row for row, names in DEFENSE_ROW_ABILITIES.items() if slug in names),
            None,
        )
        if matched_def_row:
            def_row = matched_def_row
            continue
        passive_total += passive_cost(ability, float(toughness))

    quality_value = quality_modifier(int(quality), qua_row)
    defense_value = defense_modifier(int(defense), def_row)
    toughness_value = toughness_modifier(int(toughness))

    cost = BASE_COST_FACTOR * quality_value * defense_value * toughness_value
    cost += passive_total
    return cost


def _weapon_cost(
    quality: int,
    range_value: int,
    attacks: float,
    ap: int,
    weapon_traits: Sequence[str],
    unit_traits: Sequence[str],
    allow_assault_extra: bool = True,
) -> float:
    chance = 7.0
    attacks = float(attacks if attacks is not None else 1.0)
    attacks = max(attacks, 0.0)
    ap = int(ap or 0)
    range_mod = range_multiplier(range_value)
    ap_mod = lookup_with_nearest(AP_BASE, ap)
    mult = 1.0
    q = int(quality)

    unit_set: set[str] = set()
    for trait in unit_traits:
        identifier = ability_identifier(trait)
        if identifier:
            unit_set.add(identifier)
    melee = range_value == 0

    if melee and "furia" in unit_set:
        chance += 0.65
    if not melee and "nieustepliwy" in unit_set:
        chance += 0.65
    if not melee and "wojownik" in unit_set:
        mult *= 0.5
    if melee and "strzelec" in unit_set:
        mult *= 0.5
    if not melee and "zle_strzela" in unit_set:
        q = 5
    if not melee and "dobrze_strzela" in unit_set:
        q = 4

    assault = False
    overcharge = False

    for trait in weapon_traits:
        norm = normalize_name(trait)
        if not norm:
            continue

        if norm.startswith("rozprysk") or norm.startswith("blast"):
            value = int(round(extract_number(trait)))
            if value in BLAST_MULTIPLIER:
                mult *= BLAST_MULTIPLIER[value]
                continue

        if norm.startswith("zabojczy") or norm.startswith("deadly"):
            value = int(round(extract_number(trait)))
            if value in DEADLY_MULTIPLIER:
                mult *= DEADLY_MULTIPLIER[value]
                continue

        if norm in {"rozrywajacy", "rozrywajaca", "rozrwyajaca", "rending"}:
            chance += 1.0
        elif norm in {"lanca", "lance"}:
            chance += 0.65
        elif norm in {"namierzanie", "lock on"}:
            chance += 0.35
            mult *= 1.1
            ap_mod += lookup_with_nearest(AP_NO_COVER, ap)
        elif norm in {"ciezki", "heavy"}:
            chance -= 0.35
        elif norm in {"impet", "impact"}:
            ap_mod += lookup_with_nearest(AP_LANCE, ap)
        elif norm in {"bez oslon", "bez oslony", "no cover"}:
            ap_mod += lookup_with_nearest(AP_NO_COVER, ap)
        elif norm in {"zracy", "corrosive"}:
            ap_mod += lookup_with_nearest(AP_CORROSIVE, ap)
        elif norm in {"niebezposredni", "indirect"}:
            mult *= 1.2
        elif norm in {"zuzywalny", "limited"}:
            mult *= 0.5
        elif norm in {"precyzyjny", "precise"}:
            mult *= 1.5
        elif norm in {"niezawodny", "niezawodna", "reliable"}:
            q = 2
        elif norm in {"szturmowy", "szturmowa", "assault"}:
            assault = True
        elif norm in {"bez regeneracji", "bez regegenracji", "no regen", "no regeneration"}:
            # Brak regeneracji nie zwiększa kosztu broni – cecha przeniesiona z modelu.
            continue
        elif norm in {"podkrecenie", "overcharge", "overclock"}:
            overcharge = True

    chance = max(chance - q, 1.0)
    cost = attacks * 2.0 * range_mod * chance * ap_mod * mult

    if overcharge and (not assault or range_value != 0):
        cost *= 1.4

    if assault and allow_assault_extra and range_value != 0:
        extra = _weapon_cost(
            quality,
            0,
            attacks,
            ap,
            weapon_traits,
            unit_traits,
            allow_assault_extra=False,
        )
        cost += extra

    return cost


def weapon_cost(
    weapon: models.Weapon,
    unit_quality: int = 4,
    unit_flags: dict | None = None,
) -> float:
    unit_traits = flags_to_ability_list(unit_flags)
    range_value = normalize_range_value(weapon.effective_range)
    traits = split_traits(weapon.effective_tags)
    attacks_value = weapon.effective_attacks
    cost = max(
        _weapon_cost(
            unit_quality,
            range_value,
            attacks_value,
            weapon.effective_ap,
            traits,
            unit_traits,
        ),
        0.0,
    )
    return round(cost, 2)
  
def unit_default_weapons(unit: models.Unit | None) -> list[models.Weapon]:
    if unit is None:
        return []

    weapons: list[models.Weapon] = []
    seen: set[int] = set()
    links = getattr(unit, "weapon_links", None) or []
    for link in links:
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
        for _ in range(count):
            weapons.append(link.weapon)
        seen.add(link.weapon.id)
    if unit.default_weapon:
        default_id = unit.default_weapon_id or getattr(unit.default_weapon, "id", None)
        if default_id is None or default_id not in seen:
            weapons.append(unit.default_weapon)
            if default_id is not None:
                seen.add(default_id)
    return weapons

def ability_cost(ability_link: models.UnitAbility, unit_traits: Sequence[str] | None = None) -> float:
    ability = ability_link.ability
    if not ability:
        return 0.0
    if ability.cost_hint is not None:
        return float(ability.cost_hint)
    value = None
    if ability_link.params_json:
        try:
            data = json.loads(ability_link.params_json)
        except json.JSONDecodeError:
            data = {}
        value = data.get("value")
    return ability_cost_from_name(ability.name or "", value, unit_traits)


def unit_total_cost(unit: models.Unit) -> float:
    flags = parse_flags(unit.flags)
    unit_traits = flags_to_ability_list(flags)
    cost = base_model_cost(unit.quality, unit.defense, unit.toughness, unit_traits)
    for weapon in unit_default_weapons(unit):
        cost += weapon_cost(weapon, unit.quality, flags)
    cost += sum(ability_cost(link, unit_traits) for link in unit.abilities)
    return round(cost, 2)


def roster_unit_cost(roster_unit: models.RosterUnit) -> float:
    flags = parse_flags(roster_unit.unit.flags)
    unit_traits = flags_to_ability_list(flags)
    base_value = base_model_cost(
        roster_unit.unit.quality,
        roster_unit.unit.defense,
        roster_unit.unit.toughness,
        unit_traits,
    )

    passive_cost = 0.0
    ability_costs: dict[int, float] = {}
    active_total = 0.0
    for link in getattr(roster_unit.unit, "abilities", []):
        ability = link.ability
        if not ability:
            continue
        cost_value = ability_cost(link, unit_traits)
        if ability.type == "passive":
            passive_cost += cost_value
        else:
            ability_costs[ability.id] = cost_value
            active_total += cost_value

    base_per_model = base_value + passive_cost

    def _weapon_cost_map() -> dict[int, float]:
        results: dict[int, float] = {}
        links = getattr(roster_unit.unit, "weapon_links", None) or []
        for link in links:
            weapon = link.weapon
            if not weapon or link.weapon_id is None:
                continue
            if link.weapon_id in results:
                continue
            results[link.weapon_id] = weapon_cost(
                weapon,
                roster_unit.unit.quality,
                flags,
            )
        if roster_unit.unit.default_weapon and roster_unit.unit.default_weapon_id:
            weapon_id = roster_unit.unit.default_weapon_id
            if weapon_id not in results:
                results[weapon_id] = weapon_cost(
                    roster_unit.unit.default_weapon,
                    roster_unit.unit.quality,
                    flags,
                )
        if roster_unit.selected_weapon and roster_unit.selected_weapon.id not in results:
            results[roster_unit.selected_weapon.id] = weapon_cost(
                roster_unit.selected_weapon,
                roster_unit.unit.quality,
                flags,
            )
        return results

    weapon_costs = _weapon_cost_map()

    raw_data: dict[str, Any] | None = None
    loadout_mode: str | None = None
    if roster_unit.extra_weapons_json:
        try:
            parsed = json.loads(roster_unit.extra_weapons_json)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            raw_data = parsed
            mode_value = parsed.get("mode")
            if isinstance(mode_value, str):
                loadout_mode = mode_value

    def _parse_counts(section: str) -> dict[int, int]:
        raw: dict[str, Any] = {}
        data = raw_data if isinstance(raw_data, dict) else {}
        raw_section = data.get(section) if isinstance(data, dict) else None
        if isinstance(raw_section, dict):
            raw = raw_section
        elif isinstance(raw_section, list):
            temp: dict[str, int] = {}
            for entry in raw_section:
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get("id") or entry.get("weapon_id") or entry.get("ability_id")
                if entry_id is None:
                    continue
                temp[str(entry_id)] = entry.get("per_model") or entry.get("count") or 0
            raw = temp
        counts: dict[int, int] = {}
        for raw_id, raw_value in raw.items():
            try:
                parsed_id = int(raw_id)
            except (TypeError, ValueError):
                try:
                    parsed_id = int(float(raw_id))
                except (TypeError, ValueError):
                    continue
            try:
                parsed_value = int(raw_value)
            except (TypeError, ValueError):
                try:
                    parsed_value = int(float(raw_value))
                except (TypeError, ValueError):
                    parsed_value = 0
            if parsed_value < 0:
                parsed_value = 0
            counts[parsed_id] = parsed_value
        return counts

    weapons_counts = _parse_counts("weapons") if roster_unit.extra_weapons_json else {}
    active_counts = _parse_counts("active") if roster_unit.extra_weapons_json else {}
    aura_counts = _parse_counts("aura") if roster_unit.extra_weapons_json else {}

    if roster_unit.extra_weapons_json:
        total = base_per_model * max(roster_unit.count, 1)
        total_mode = loadout_mode == "total"
        model_multiplier = max(roster_unit.count, 1)

        def _to_total(value: int) -> int:
            safe_value = max(int(value), 0)
            return safe_value if total_mode else safe_value * model_multiplier

        for weapon_id, stored_count in weapons_counts.items():
            cost_value = weapon_costs.get(weapon_id)
            if cost_value is None:
                continue
            total += cost_value * _to_total(stored_count)
        for ability_id, stored_count in {**active_counts, **aura_counts}.items():
            cost_value = ability_costs.get(ability_id)
            if cost_value is None:
                continue
            total += cost_value * _to_total(stored_count)
        return round(total, 2)

    legacy_unit_cost = base_per_model + active_total
    default_weapons = unit_default_weapons(roster_unit.unit)
    if roster_unit.selected_weapon:
        legacy_unit_cost += weapon_cost(
            roster_unit.selected_weapon,
            roster_unit.unit.quality,
            flags,
        )
    else:
        for weapon in default_weapons:
            legacy_unit_cost += weapon_cost(
                weapon,
                roster_unit.unit.quality,
                flags,
            )

    total = legacy_unit_cost * max(roster_unit.count, 1)
    return round(total, 2)


def roster_total(roster: models.Roster) -> float:
    return round(sum(roster_unit_cost(ru) for ru in roster.roster_units), 2)


def update_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for ru in roster_units:
        ru.cached_cost = roster_unit_cost(ru)
