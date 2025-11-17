"""Kalkulator kosztów jednostek zgodny z arkuszem VBA."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from .. import models
from ..data import abilities as ability_catalog
from .utils import passive_flags_to_payload


MORALE_ABILITY_MULTIPLIERS = {
    "nieustraszony": 0.5,
    "ucieczka": 0.5,
    "stracency": 0.5,
}

DEFENSE_BASE_VALUES = {2: 2.0, 3: 1.67, 4: 1.33, 5: 1.0, 6: 0.8}
DEFENSE_ABILITY_MODIFIERS = {
    "delikatny": {2: -0.05, 3: -0.07, 4: -0.08, 5: -0.1, 6: -0.13},
    "niewrazliwy": {2: 0.05, 3: 0.1, 4: 0.2, 5: 0.3, 6: 0.35},
    "regeneracja": {2: 1.0, 3: 0.65, 4: 0.5, 5: 0.45, 6: 0.4},
    "waagh": {2: -0.03, 3: -0.03, 4: -0.03, 5: -0.02, 6: -0.01},
}

TOUGHNESS_SPECIAL = {1: 1.0, 2: 2.15, 3: 3.5}

DEFENSE_ABILITY_SLUGS = set(DEFENSE_ABILITY_MODIFIERS)

RANGE_TABLE = {0: 0.6, 12: 0.65, 18: 1.0, 24: 1.25, 30: 1.45, 36: 1.55}

CAUTIOUS_HIT_BONUS = {0: 0.0, 12: 0.0, 18: 0.5, 24: 0.7, 30: 0.8, 36: 0.9}

AP_BASE = {-1: 0.8, 0: 1.0, 1: 1.5, 2: 1.9, 3: 2.25, 4: 2.5, 5: 2.65}
AP_LANCE = {-1: 0.15, 0: 0.35, 1: 0.3, 2: 0.25, 3: 0.15, 4: 0.1, 5: 0.05}
AP_NO_COVER = {-1: 0.1, 0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05}
AP_CORROSIVE = {-1: 0.05, 0: 0.05, 1: 0.1, 2: 0.25, 3: 0.4, 4: 0.5, 5: 0.55}
WAAGH_AP_MODIFIER = {-1: 0.01, 0: 0.02, 1: 0.05, 2: 0.04, 3: 0.04, 4: 0.03, 5: 0.02}

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


ROLE_SLUGS = {"wojownik", "strzelec"}


@dataclass
class PassiveState:
    payload: list[dict[str, Any]]
    counts: dict[str, int]
    traits: list[str]


def _ensure_extra_data(extra: Any) -> dict[str, Any] | None:
    if isinstance(extra, dict):
        return extra
    if isinstance(extra, str):
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _passive_payload(unit: models.Unit | None) -> list[dict[str, Any]]:
    if unit is None:
        return []
    payload: list[dict[str, Any]] = []
    for entry in passive_flags_to_payload(getattr(unit, "flags", None)):
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        is_default = bool(entry.get("is_default", False))
        payload.append(
            {
                "slug": slug,
                "label": entry.get("label") or slug,
                "value": entry.get("value"),
                "is_default": is_default,
                "default_count": 1 if is_default else 0,
            }
        )
    return payload


def _parse_passive_counts(extra: dict[str, Any] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    if not isinstance(extra, dict):
        return result
    raw_section = extra.get("passive")
    if isinstance(raw_section, dict):
        iterable = raw_section.items()
    elif isinstance(raw_section, list):
        iterable = []
        for entry in raw_section:
            if not isinstance(entry, dict):
                continue
            key = entry.get("slug") or entry.get("id")
            if key is None:
                continue
            iterable.append((key, entry.get("count") or entry.get("per_model") or entry.get("enabled")))
    else:
        return result
    for raw_key, raw_value in iterable:
        slug = str(raw_key).strip()
        if not slug:
            continue
        value = raw_value
        if isinstance(value, bool):
            result[slug] = 1 if value else 0
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            try:
                parsed = int(float(value))
            except (TypeError, ValueError):
                parsed = 1 if value else 0
        result[slug] = 1 if parsed > 0 else 0
    return result


def _active_traits_from_payload(
    payload: Sequence[dict[str, Any]], counts: dict[str, int]
) -> list[str]:
    traits: list[str] = []
    for entry in payload:
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        default_count = int(entry.get("default_count") or 0)
        selected = counts.get(str(slug), default_count)
        if selected <= 0:
            continue
        value = entry.get("value")
        if isinstance(value, bool):
            if value:
                traits.append(slug)
            continue
        if value is None:
            traits.append(slug)
            continue
        value_str = str(value).strip()
        if not value_str or value_str.casefold() in {"true", "yes"}:
            traits.append(slug)
        elif value_str.casefold() in {"false", "no", "0"}:
            continue
        else:
            traits.append(f"{slug}({value_str})")
    return traits


def compute_passive_state(
    unit: models.Unit | None, extra: dict[str, Any] | str | None = None
) -> PassiveState:
    payload = _passive_payload(unit)
    extra_data = _ensure_extra_data(extra)
    counts = _parse_passive_counts(extra_data)
    traits = _active_traits_from_payload(payload, counts)
    return PassiveState(payload=payload, counts=counts, traits=traits)


def _passive_flag_maps(passive_state: PassiveState) -> tuple[dict[str, int], dict[str, int]]:
    default_map: dict[str, int] = {}
    selected_map: dict[str, int] = {}
    for entry in passive_state.payload:
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            continue
        try:
            default_count = int(entry.get("default_count") or 0)
        except (TypeError, ValueError):
            default_count = 0
        default_flag = 1 if default_count > 0 else 0
        selected_value = passive_state.counts.get(str(slug), default_flag)
        selected_flag = 1 if selected_value else 0
        identifiers: set[str] = set()
        for token in (slug, entry.get("label")):
            if not token:
                continue
            identifiers.add(normalize_name(token))
            ident = ability_identifier(token)
            if ident:
                identifiers.add(ident)
        for ident in {value for value in identifiers if value}:
            default_map[ident] = default_flag
            selected_map[ident] = selected_flag
    return default_map, selected_map


def _strip_role_traits(traits: Sequence[str]) -> list[str]:
    clean: list[str] = []
    for trait in traits:
        identifier = ability_identifier(trait)
        if identifier in ROLE_SLUGS:
            continue
        clean.append(trait)
    return clean


def _with_role_trait(traits: Sequence[str], slug: str | None) -> list[str]:
    base = list(traits)
    if slug and slug in ROLE_SLUGS:
        base.append(slug)
    return base


def _ascii_letters(value: str) -> str:
    result: list[str] = []
    for char in value:
        if unicodedata.combining(char):
            continue
        if ord(char) < 128:
            result.append(char)
            continue
        name = unicodedata.name(char, "")
        if "LETTER" in name:
            base = name.split("LETTER", 1)[1].strip()
            if " WITH " in base:
                base = base.split(" WITH ", 1)[0].strip()
            if " SIGN" in base:
                base = base.split(" SIGN", 1)[0].strip()
            if " DIGRAPH" in base:
                base = base.split(" DIGRAPH", 1)[0].strip()
            tokens = base.split()
            if len(tokens) > 1 and len(tokens[-1]) == 1:
                base = tokens[-1]
            else:
                base = base.replace(" ", "")
            if not base:
                continue
            if "SMALL" in name:
                result.append(base.lower())
            else:
                result.append(base.upper())
        # Ignore characters without a useful letter mapping.
    return "".join(result)


def normalize_name(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = _ascii_letters(value)
    value = value.replace("-", " ").replace("_", " ")
    value = re.sub(r"[!?]+$", "", value)
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
        raw_name = str(key).strip()
        if not raw_name:
            continue
        is_optional = False
        name = raw_name
        while name.endswith(("?", "!")):
            if name.endswith("!"):
                name = name[:-1].strip()
                continue
            if name.endswith("?"):
                name = name[:-1].strip()
                is_optional = True
                continue
            break
        if not name:
            continue
        slug = ability_catalog.slug_for_name(name) or name
        if is_optional:
            # Zdolności oznaczone znakiem zapytania są dostępne do kupienia,
            # ale nie wchodzą w skład podstawowego profilu jednostki.
            # Nie powinny więc wpływać na koszt ani statystyki bazowe.
            continue
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


def ability_choices(ability: str | None) -> list[str]:
    identifier = ability_identifier(ability)
    if not identifier:
        return []
    normalized = identifier.replace("\\", "/")
    if "/" not in normalized:
        return [identifier]
    options: list[str] = []
    for part in normalized.split("/"):
        part = part.strip()
        if not part:
            continue
        slug = ability_catalog.slug_for_name(part)
        if slug:
            options.append(slug)
        else:
            options.append(normalize_name(part))
    return options or [identifier]


def unit_trait_variants(unit_flags: dict | None) -> list[tuple[str, ...]]:
    base_traits = flags_to_ability_list(unit_flags)
    variants: list[tuple[str, ...]] = [tuple()]
    for trait in base_traits:
        options = ability_choices(trait)
        if not options:
            continue
        next_variants: list[tuple[str, ...]] = []
        for existing in variants:
            for option in options:
                next_variants.append(existing + (option,))
        variants = next_variants if next_variants else variants
    if not variants:
        return [tuple()]
    dedup: dict[tuple[str, ...], None] = {}
    for variant in variants:
        dedup.setdefault(variant, None)
    return list(dedup.keys())


def split_traits(text: str | None) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;]", text) if part.strip()]


def clamp_quality(value: int) -> int:
    return max(2, min(6, int(value)))


def clamp_defense(value: int) -> int:
    return max(2, min(6, int(value)))


def morale_modifier(quality: int, penalty_multiplier: float = 1.0) -> float:
    quality = clamp_quality(quality)
    penalty = max(float(penalty_multiplier), 0.0)
    return 1.3 - (quality - 1) / 10.0 * penalty


def defense_modifier(defense: int, ability_slugs: Iterable[str] | None = None) -> float:
    defense = clamp_defense(defense)
    value = DEFENSE_BASE_VALUES[defense]
    if ability_slugs:
        for slug in ability_slugs:
            modifier_map = DEFENSE_ABILITY_MODIFIERS.get(slug)
            if modifier_map:
                value += modifier_map.get(defense, 0.0)
    return value


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
    base = base.rstrip("?!").strip()
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
    if slug == "instynkt":
        return (-1.0 if not aura else 1.0) * tou
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
    if slug == "dywersant":
        return 10.0
    if slug == "zdobywca":
        return 3.0 * tou
    if slug == "straznik":
        return 3.0 * tou

    if aura:
        if slug in {"nieustraszony", "ucieczka", "stracency"}:
            return 1.5 * tou
        if slug == "delikatny":
            return 0.5 * tou
        if slug == "niewrazliwy":
            return 2.0 * tou
        if slug == "regeneracja":
            return 3.5 * tou
        if slug == "furia":
            return 3.0 * tou
        if slug == "przygotowanie":
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
    *,
    toughness: int | float | None = None,
    quality: int | None = None,
    defense: int | None = None,
    weapons: Sequence[models.Weapon] | None = None,
) -> float:
    desc = normalize_name(name)
    if not desc:
        return 0.0

    abilities: list[str] = list(unit_abilities or [])
    slug = ability_identifier(name)

    def _contains_slug(items: Sequence[str], needle: str | None) -> bool:
        if not needle:
            return False
        for element in items:
            if ability_identifier(element) == needle:
                return True
        return False

    if slug and not _contains_slug(abilities, slug):
        if value is not None and str(value).strip():
            abilities.append(f"{slug}({value})")
        else:
            abilities.append(slug)

    abilities_without: list[str]
    if slug:
        abilities_without = []
        removed = False
        for item in abilities:
            if not removed and ability_identifier(item) == slug:
                removed = True
                continue
            abilities_without.append(item)
    else:
        abilities_without = list(abilities)

    ability_set: set[str] = set()
    for item in abilities:
        identifier = ability_identifier(item)
        if identifier:
            ability_set.add(identifier)

    row_delta: float | None = None
    if (
        slug
        and quality is not None
        and defense is not None
        and toughness is not None
        and abilities_without != abilities
        and (slug in MORALE_ABILITY_MULTIPLIERS or slug in DEFENSE_ABILITY_SLUGS)

    ):
        row_delta = base_model_cost(
            int(quality),
            int(defense),
            int(float(toughness)),
            abilities,
        ) - base_model_cost(
            int(quality),
            int(defense),
            int(float(toughness)),
            abilities_without,
        )

    weapon_delta = 0.0
    if (
        weapons
        and slug
        and quality is not None
        and abilities_without != abilities
    ):
        traits_with = abilities
        traits_without = abilities_without
        total_with = 0.0
        total_without = 0.0
        for weapon in weapons:
            total_with += weapon_cost(weapon, int(quality), traits_with)
            total_without += weapon_cost(weapon, int(quality), traits_without)
        weapon_delta = total_with - total_without
        if slug == "przygotowanie":
            weapon_delta = 0.0

    if desc.startswith("transport"):
        capacity = extract_number(value or name)
        multiplier = 1.0
        for options, value in TRANSPORT_MULTIPLIERS:
            if ability_set & options:
                multiplier = value
        base_result = capacity * multiplier
    elif desc.startswith("aura"):
        ability_slug, aura_range = _parse_aura_value(name, value)
        cost = passive_cost(ability_slug, 8.0, True)
        if abs(aura_range - 12.0) < 1e-6:
            cost *= 2.0
        base_result = cost
    elif desc.startswith("mag"):
        base_result = 8.0 * extract_number(value or name)
    elif desc == "przekaznik":
        base_result = 4.0
    elif desc == "koordynacja":
        base_result = 45.0
    elif slug == "latanie":
        base_result = 20.0
    elif slug == "mobilizacja":
        base_result = 30.0
    elif slug == "przepowiednia":
        base_result = 45.0
    elif slug == "presja":
        base_result = 45.0
    elif desc.startswith("rozkaz"):
        ability_ref = value or (desc.split(":", 1)[1].strip() if ":" in desc else "")
        ability_slug = ability_catalog.slug_for_name(ability_ref) or ability_identifier(ability_ref)
        base_result = passive_cost(ability_slug, 10.0, True)
    elif desc == "radio":
        base_result = 3.0
    elif slug == "ociezalosc":
        base_result = 20.0
    elif desc == "spaczenie":
        base_result = 30.0
    else:
        tou_value = float(toughness) if toughness is not None else 1.0
        definition = ability_catalog.find_definition(slug) if slug else None
        if slug == "przygotowanie":
            base_result = 0.0
        elif definition and definition.type == "passive":
            base_result = passive_cost(name, tou_value)
        elif slug and not definition:
            base_result = passive_cost(name, tou_value)
        else:
            base_result = 0.0

    if row_delta is not None:
        base_result = row_delta

    return base_result + weapon_delta


def base_model_cost(
    quality: int,
    defense: int,
    toughness: int,
    abilities: Sequence[str] | None,
) -> float:
    ability_list = list(abilities or [])

    morale_multiplier = 1.0
    applied_morale_modifiers: set[str] = set()
    defense_abilities: list[str] = []
    passive_total = 0.0

    for ability in ability_list:
        slug = ability_identifier(ability)
        norm = slug or normalize_name(ability)
        if not norm:
            continue
        if slug in MORALE_ABILITY_MULTIPLIERS and slug not in applied_morale_modifiers:
            morale_multiplier *= MORALE_ABILITY_MULTIPLIERS[slug]
            applied_morale_modifiers.add(slug)
            continue
        if slug in DEFENSE_ABILITY_SLUGS:
            defense_abilities.append(slug)
            continue
        passive_total += passive_cost(ability, float(toughness))

    morale_value = morale_modifier(int(quality), morale_multiplier)
    defense_value = defense_modifier(int(defense), defense_abilities)
    toughness_value = toughness_modifier(int(toughness))

    cost = BASE_COST_FACTOR * morale_value * defense_value * toughness_value
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
    base_ap = int(ap or 0)
    range_mod = range_multiplier(range_value)
    ap_mod = lookup_with_nearest(AP_BASE, base_ap)
    mult = 1.0
    q = int(quality)

    unit_set: set[str] = set()
    for trait in unit_traits:
        identifier = ability_identifier(trait)
        if identifier:
            unit_set.add(identifier)
    melee = range_value == 0

    waagh_penalty = 0.0
    if "waagh" in unit_set:
        waagh_penalty = lookup_with_nearest(WAAGH_AP_MODIFIER, base_ap)

    if melee and "furia" in unit_set:
        chance += 0.65
    if not melee and "przygotowanie" in unit_set:
        chance += 0.65
    if "szpica" in unit_set:
        chance += 0.5
    if "ostrozny" in unit_set:
        chance += lookup_with_nearest(CAUTIOUS_HIT_BONUS, range_value)
    if not melee and "wojownik" in unit_set:
        mult *= 0.5
    if melee and "strzelec" in unit_set:
        mult *= 0.5
    if not melee and "zle_strzela" in unit_set:
        q = 5
    if not melee and "dobrze_strzela" in unit_set:
        q = 4
    if "zemsta" in unit_set:
        mult *= 1.1

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

        if norm in {"seria", "rozrywajacy", "rozrywajaca", "rozrwyajaca", "rending"}:
            chance += 1.0
        elif norm in {"lanca", "lance"}:
            chance += 0.65
        elif norm in {"namierzanie", "lock on"}:
            chance += 0.35
            mult *= 1.1
            ap_mod += lookup_with_nearest(AP_NO_COVER, base_ap)
        elif norm in {"impet", "impact"}:
            ap_mod += lookup_with_nearest(AP_LANCE, base_ap)
        elif norm in {"bez oslon", "bez oslony", "no cover"}:
            ap_mod += lookup_with_nearest(AP_NO_COVER, base_ap)
        elif norm in {"zracy", "corrosive"}:
            ap_mod += lookup_with_nearest(AP_CORROSIVE, base_ap)
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
        elif norm in {
            "brutalny",
            "brutalna",
            "brutal",
            "bez regeneracji",
            "bez regegenracji",
            "no regen",
            "no regeneration",
        }:
            mult *= 1.1
        elif norm in {"podkrecenie", "overcharge", "overclock"}:
            overcharge = True

    if waagh_penalty:
        ap_mod = max(ap_mod - waagh_penalty, 0.0)

    chance = max(chance - q, 1.0)
    cost = attacks * 2.0 * range_mod * chance * ap_mod * mult

    if overcharge and (not assault or range_value != 0):
        cost *= 1.4

    if assault and allow_assault_extra and range_value != 0:
        extra = _weapon_cost(
            quality,
            0,
            attacks,
            base_ap,
            weapon_traits,
            unit_traits,
            allow_assault_extra=False,
        )
        if overcharge:
            cost += extra + max(cost, extra) * 0.4
        else:
            cost += extra
    else:
        if overcharge:
            cost *= 1.4
    return cost


def weapon_cost(
    weapon: models.Weapon,
    unit_quality: int = 4,
    unit_flags: dict | Sequence[str] | None = None,
    *,
    use_cached: bool = True,
) -> float:
    if isinstance(unit_flags, dict):
        unit_traits = flags_to_ability_list(unit_flags)
    elif unit_flags is None:
        unit_traits = []
    else:
        unit_traits = list(unit_flags)

    # Standard armory views should reuse cached weapon costs when possible.
    if use_cached and unit_quality == 4 and not unit_traits:
        cached = getattr(weapon, "effective_cached_cost", None)
        if isinstance(cached, (int, float)) and math.isfinite(cached):
            return round(max(float(cached), 0.0), 2)

    range_value = normalize_range_value(weapon.effective_range)
    traits = split_traits(weapon.effective_tags)
    attacks_value = weapon.effective_attacks
    cost: float | None = None
    cost = _weapon_cost(
        unit_quality,
        range_value,
        attacks_value,
        weapon.effective_ap,
        traits,
        unit_traits,
    )

    if cost is None:
        cost = 0.0
    cost = max(cost, 0.0)
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

def _ability_link_is_default(link: models.UnitAbility) -> bool:
    def _coerce_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return False
            lowered = text.casefold()
            if lowered in {"true", "yes", "1", "on"}:
                return True
            if lowered in {"false", "no", "0", "off"}:
                return False
            try:
                return float(text) != 0.0
            except ValueError:
                return True
        return bool(value)

    params_json = getattr(link, "params_json", None)
    if not params_json:
        return False
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        return False
    default_flag: bool | None = None
    for key in ("default", "is_default"):
        if key in params:
            default_flag = _coerce_bool(params.get(key))
            break
    if default_flag is None and "default_count" in params:
        try:
            return int(params.get("default_count") or 0) > 0
        except (TypeError, ValueError):
            return False
    return bool(default_flag)


def ability_cost(
    ability_link: models.UnitAbility,
    unit_traits: Sequence[str] | None = None,
    toughness: int | float | None = None,
) -> float:
    ability = ability_link.ability
    if not ability:
        return 0.0
    if ability.cost_hint is not None:
        return float(ability.cost_hint)
    unit = getattr(ability_link, "unit", None)
    value = None
    if ability_link.params_json:
        try:
            data = json.loads(ability_link.params_json)
        except json.JSONDecodeError:
            data = {}
        value = data.get("value")
    base_toughness = toughness
    if base_toughness is None and unit is not None:
        base_toughness = getattr(unit, "toughness", None)
    return ability_cost_from_name(
        ability.name or "",
        value,
        unit_traits,
        toughness=base_toughness,
        quality=getattr(unit, "quality", None) if unit is not None else None,
        defense=getattr(unit, "defense", None) if unit is not None else None,
        weapons=unit_default_weapons(unit) if unit is not None else None,
    )


def unit_total_cost(unit: models.Unit) -> float:
    passive_state = compute_passive_state(unit)
    unit_traits = passive_state.traits
    cost = base_model_cost(unit.quality, unit.defense, unit.toughness, unit_traits)
    for weapon in unit_default_weapons(unit):
        cost += weapon_cost(weapon, unit.quality, unit_traits)
    cost += sum(
        ability_cost(link, unit_traits, toughness=unit.toughness)
        for link in unit.abilities
        if _ability_link_is_default(link)
    )
    return round(cost, 2)


def unit_typical_total_cost(
    unit: models.Unit,
    model_count: int | None = None,
    *,
    per_model: float | None = None,
) -> float:
    if per_model is None:
        per_model_value = unit_total_cost(unit)
    else:
        try:
            per_model_value = float(per_model)
        except (TypeError, ValueError):
            per_model_value = unit_total_cost(unit)
    if model_count is None:
        try:
            model_count = unit.typical_model_count
        except AttributeError:  # pragma: no cover - compatibility
            model_count = getattr(unit, "typical_models", 1)
    try:
        count = int(model_count)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    return round(per_model_value * count, 2)


def roster_unit_role_totals(
    roster_unit: models.RosterUnit,
    payload: dict[str, dict[str, int]] | None = None,
) -> dict[str, float]:
    unit = getattr(roster_unit, "unit", None)
    if unit is None:
        return {"wojownik": 0.0, "strzelec": 0.0}

    extra_data = (
        payload
        if isinstance(payload, dict)
        else _ensure_extra_data(getattr(roster_unit, "extra_weapons_json", None))
    ) or {}
    raw_data: dict[str, Any] = extra_data if isinstance(extra_data, dict) else {}

    mode_value = raw_data.get("mode")
    loadout_mode: str | None = mode_value if isinstance(mode_value, str) else None

    passive_state = compute_passive_state(unit, raw_data)
    base_traits = _strip_role_traits(passive_state.traits)
    default_weapons = unit_default_weapons(unit)
    has_massive_trait = any(
        ability_identifier(trait) == "masywny" for trait in base_traits
    )

    def _parse_counts(section: str) -> dict[int, int]:
        raw_section = raw_data.get(section)
        result: dict[int, int] = {}
        if isinstance(raw_section, dict):
            items = raw_section.items()
        elif isinstance(raw_section, list):
            temp: list[tuple[Any, Any]] = []
            for entry in raw_section:
                if not isinstance(entry, dict):
                    continue
                entry_id = (
                    entry.get("loadout_key")
                    or entry.get("key")
                    or entry.get("id")
                    or entry.get("weapon_id")
                    or entry.get("ability_id")
                )
                if entry_id is None:
                    continue
                temp.append((entry_id, entry.get("per_model") or entry.get("count") or 0))
            items = temp
        else:
            items = []
        for raw_id, raw_value in items:
            raw_id_str = str(raw_id)
            base_id = raw_id_str.split(":", 1)[0]
            try:
                parsed_id = int(base_id)
            except (TypeError, ValueError):
                try:
                    parsed_id = int(float(base_id))
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
            result[parsed_id] = parsed_value
        return result

    weapons_counts = _parse_counts("weapons")
    active_counts = _parse_counts("active")
    aura_counts = _parse_counts("aura")
    passive_counts = passive_state.counts

    total_mode = loadout_mode == "total"
    model_multiplier = max(int(getattr(roster_unit, "count", 0)), 0)
    model_count = max(model_multiplier, 1)

    ability_multiplier = (
        0 if model_multiplier == 0 else 1 if has_massive_trait else model_count
    )

    def _to_total(value: int, *, ability: bool = False) -> int:
        safe_value = max(int(value), 0)
        if total_mode:
            return safe_value
        multiplier = ability_multiplier if ability else model_count
        return safe_value * multiplier

    def _weapon_cost_map(current_traits: Sequence[str]) -> dict[int, float]:
        results: dict[int, float] = {}
        links = getattr(unit, "weapon_links", None) or []
        for link in links:
            weapon = link.weapon
            if not weapon or link.weapon_id is None:
                continue
            if link.weapon_id in results:
                continue
            results[link.weapon_id] = weapon_cost(
                weapon,
                unit.quality,
                current_traits,
            )
        if unit.default_weapon and unit.default_weapon_id is not None:
            weapon_id = unit.default_weapon_id
            if weapon_id not in results:
                results[weapon_id] = weapon_cost(
                    unit.default_weapon,
                    unit.quality,
                    current_traits,
                )
        return results

    def _passive_entries(current_traits: Sequence[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for entry in passive_state.payload:
            slug = str(entry.get("slug") or "").strip()
            if not slug or slug in ROLE_SLUGS:
                continue
            label = entry.get("label") or slug
            value = entry.get("value")
            default_count = int(entry.get("default_count") or 0)
            cost_value = ability_cost_from_name(
                label or slug,
                value,
                current_traits,
                toughness=unit.toughness,
                quality=unit.quality,
                defense=unit.defense,
                weapons=default_weapons,
            )
            entries.append(
                {
                    "slug": slug,
                    "default_count": default_count,
                    "cost": float(cost_value),
                }
            )
        return entries

    passive_defaults, _ = _passive_flag_maps(passive_state)

    def _passive_default_flag(name: str | None) -> int | None:
        for key in (ability_identifier(name), normalize_name(name)):
            if key and key in passive_defaults:
                return passive_defaults[key]
        return None

    def _ability_cost_map(current_traits: Sequence[str]) -> tuple[dict[int, float], float, float]:
        ability_map: dict[int, float] = {}
        passive_total = 0.0
        active_total = 0.0
        links = [link for link in getattr(unit, "abilities", []) if link.ability]
        links.sort(
            key=lambda link: (
                getattr(link, "position", 0),
                getattr(link, "id", 0) or 0,
            )
        )
        for link in links:
            ability = link.ability
            cost_value = ability_cost(
                link,
                current_traits,
                toughness=unit.toughness,
            )
            if ability.type == "passive":
                default_flag = _passive_default_flag(ability.name)
                if default_flag is None or default_flag > 0:
                    passive_total += cost_value
            else:
                ability_map[ability.id] = cost_value
                active_total += cost_value
        return ability_map, passive_total, active_total

    def _compute_total(current_traits: Sequence[str]) -> float:
        ability_map, passive_total, _ = _ability_cost_map(current_traits)
        base_value = base_model_cost(
            unit.quality,
            unit.defense,
            unit.toughness,
            current_traits,
        )
        base_per_model = base_value
        passive_entries = _passive_entries(current_traits)
        weapon_costs = _weapon_cost_map(current_traits)

        total = base_per_model * model_count
        if passive_total:
            total += passive_total * (1 if total_mode else ability_multiplier)
        for weapon_id, stored_count in weapons_counts.items():
            cost_value = weapon_costs.get(weapon_id)
            if cost_value is None:
                continue
            total += cost_value * _to_total(stored_count)
        for ability_id, stored_count in {**active_counts, **aura_counts}.items():
            cost_value = ability_map.get(ability_id)
            if cost_value is None:
                continue
            total += cost_value * _to_total(stored_count, ability=True)
        passive_diff = 0.0
        for entry in passive_entries:
            slug = entry.get("slug")
            if not slug:
                continue
            default_value = 1 if entry.get("default_count") else 0
            selected_value = passive_counts.get(str(slug), default_value)
            selected_flag = 1 if selected_value else 0
            diff = selected_flag - default_value
            if diff == 0:
                continue
            cost_value = float(entry.get("cost") or 0.0)
            if cost_value == 0.0:
                continue
            passive_diff += cost_value * diff
        if passive_diff:
            total += passive_diff * (1 if total_mode else ability_multiplier)
        return round(total, 2)

    warrior_total = _compute_total(_with_role_trait(base_traits, "wojownik"))
    shooter_total = _compute_total(_with_role_trait(base_traits, "strzelec"))
    return {"wojownik": warrior_total, "strzelec": shooter_total}


def roster_unit_cost(roster_unit: models.RosterUnit) -> float:
    totals = roster_unit_role_totals(roster_unit)
    warrior = float(totals.get("wojownik") or 0.0)
    shooter = float(totals.get("strzelec") or 0.0)
    return round(max(warrior, shooter), 2)


def roster_total(roster: models.Roster) -> float:
    total = 0.0
    for roster_unit in getattr(roster, "roster_units", []):
        cost_value = getattr(roster_unit, "cached_cost", None)
        if cost_value is None:
            cost_value = roster_unit_cost(roster_unit)
            if hasattr(roster_unit, "cached_cost"):
                roster_unit.cached_cost = cost_value
        try:
            numeric = float(cost_value)
        except (TypeError, ValueError):
            continue
        total += numeric
    return round(total, 2)


def ensure_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for roster_unit in roster_units:
        if getattr(roster_unit, "cached_cost", None) is None:
            roster_unit.cached_cost = roster_unit_cost(roster_unit)


def update_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for ru in roster_units:
        ru.cached_cost = roster_unit_cost(ru)
