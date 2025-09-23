"""Kalkulator kosztów jednostek zgodny z arkuszem VBA."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

from .. import models
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

QUALITY_ROW_ABILITIES = {"nieustraszony", "stracency", "fearless", "expendable"}

DEFENSE_ROW_ABILITIES = {
    2: {"delikatny", "fragile"},
    3: {"niewrazliwy", "invulnerable", "inv"},
    4: {"regeneracja", "regen", "regeneration"},
}

RANGE_TABLE = {0: 0.6, 12: 0.65, 18: 1.0, 24: 1.25, 30: 1.45, 36: 1.55}

AP_BASE = {-1: 0.8, 0: 1.0, 1: 1.5, 2: 1.9, 3: 2.25, 4: 2.5, 5: 2.65}
AP_LANCE = {-1: 0.15, 0: 0.35, 1: 0.3, 2: 0.25, 3: 0.15, 4: 0.1, 5: 0.05}
AP_NO_COVER = {-1: 0.1, 0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05}
AP_CORROSIVE = {-1: 0.05, 0: 0.05, 1: 0.1, 2: 0.25, 3: 0.4, 4: 0.5, 5: 0.55}

BLAST_MULTIPLIER = {2: 1.95, 3: 2.8, 6: 4.3}
DEADLY_MULTIPLIER = {2: 1.9, 3: 2.6, 6: 3.8}

TRANSPORT_MULTIPLIERS = [
    ({"samolot", "aircraft"}, 3.5),
    ({"zasadzka", "ambush", "zwiadowca", "scout"}, 2.5),
    ({"latajacy", "latajaca", "lata", "flying"}, 1.5),
    ({"szybki", "szybka", "szybcy", "fast", "zwinny", "zwinna", "agile"}, 1.25),
]


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
        if isinstance(value, bool):
            if value:
                abilities.append(name)
            continue
        if value is None:
            abilities.append(name)
            continue
        value_str = str(value).strip()
        if not value_str or value_str.casefold() in {"true", "yes"}:
            abilities.append(name)
        else:
            abilities.append(f"{name}({value_str})")
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


def passive_cost(ability_name: str, tou: float = 1.0, aura: bool = False) -> float:
    norm = normalize_name(ability_name)
    if not norm:
        return 0.0

    tou = float(tou)

    if norm in {"zasadzka", "ambush"}:
        return 2.0 * tou
    if norm in {"zwiadowca", "scout"}:
        return 2.0 * tou
    if norm in {"szybki", "szybka", "szybcy", "fast"}:
        return 1.0 * tou
    if norm in {"wolny", "slow"}:
        return -1.0 * tou
    if norm in {"harcownik", "skirmisher"}:
        return 1.5 * tou
    if norm in {"nieruchomy", "immobile"}:
        return 2.5 * tou
    if norm in {"zwinny", "agile"}:
        return 0.5 * tou
    if norm in {"niezgrabny", "niezgrabna", "clumsy"}:
        return -0.5 * tou
    if norm in {"latajacy", "latajaca", "lata", "flying"}:
        return 1.0 * tou
    if norm in {"samolot", "aircraft"}:
        return 3.0 * tou
    if norm in {"kontra", "counter"}:
        return 2.0 * tou
    if norm in {"maskowanie", "camouflage", "stealth"}:
        return 2.0 * tou
    if norm in {"okopany", "fortified", "entrenched"}:
        return 1.0 * tou
    if norm in {"tarcza", "shield"}:
        return 1.25 * tou
    if norm in {"straznik", "guardian", "overwatch"}:
        return 3.0 * tou

    if aura:
        if norm in {"nieustraszony", "stracency", "fearless", "expendable"}:
            return 1.5 * tou
        if norm in {"delikatny", "fragile"}:
            return 0.5 * tou
        if norm in {"niewrazliwy", "invulnerable", "inv"}:
            return 2.0 * tou
        if norm in {"regeneracja", "regen", "regeneration"}:
            return 3.5 * tou
        if norm in {"furia", "furious"}:
            return 3.0 * tou
        if norm in {"nieustepliwy", "nieustepliwi", "relentless"}:
            return 3.5 * tou

    if norm.startswith("strach") or norm.startswith("fear ") or norm.startswith("fear(") or norm == "fear":
        value = extract_number(norm)
        return 0.75 * value

    return 0.0


def ability_cost_from_name(name: str, unit_abilities: Sequence[str] | None = None) -> float:
    desc = normalize_name(name)
    if not desc:
        return 0.0

    ability_set = {normalize_name(item) for item in unit_abilities or []}

    if desc.startswith("transport"):
        capacity = extract_number(name)
        multiplier = 1.0
        for options, value in TRANSPORT_MULTIPLIERS:
            if ability_set & options:
                multiplier = value
        return capacity * multiplier

    if desc.startswith("aura"):
        aura_range = 0.0
        ability_name = ""
        if desc.startswith("aura("):
            match = re.match(r"aura\(([^)]+)\)\s*(.*)", desc)
            if match:
                aura_range = extract_number(match.group(1))
                ability_name = match.group(2).strip()
        elif desc.startswith("aura:"):
            ability_name = desc.split(":", 1)[1].strip()
        else:
            ability_name = desc[4:].strip()

        cost = passive_cost(ability_name, 8.0, True)
        if abs(aura_range - 12.0) < 1e-6:
            cost *= 2.0
        return cost

    if desc.startswith("mag"):
        return 8.0 * extract_number(name)

    if desc in {"przekaznik", "relay"}:
        return 4.0

    if desc in {"latanie", "patching", "repair"}:
        return 20.0

    if desc.startswith("rozkaz") or desc.startswith("order"):
        ability_name = desc.split(":", 1)[1].strip() if ":" in desc else ""
        return passive_cost(ability_name, 10.0, True)

    if desc in {"radio", "vox"}:
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
        norm = normalize_name(ability)
        if not norm:
            continue
        if norm in QUALITY_ROW_ABILITIES:
            qua_row = 2
            continue
        matched_def_row = next(
            (row for row, names in DEFENSE_ROW_ABILITIES.items() if norm in names),
            None,
        )
        if matched_def_row:
            def_row = matched_def_row
            continue
        passive_total += passive_cost(ability, float(toughness))

    quality_value = quality_modifier(int(quality), qua_row)
    defense_value = defense_modifier(int(defense), def_row)
    toughness_value = toughness_modifier(int(toughness))

    cost = 5.0 * quality_value * defense_value * toughness_value
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

    unit_set = {normalize_name(trait) for trait in unit_traits}
    melee = range_value == 0

    if melee and unit_set & {"furia", "furious"}:
        chance += 0.65
    if not melee and unit_set & {"nieustepliwy", "nieustepliwi", "relentless"}:
        chance += 0.65
    if not melee and unit_set & {"wojownik", "wojownicy", "fighter"}:
        mult *= 0.5
    if melee and unit_set & {"strzelec", "strzelcy", "shooter"}:
        mult *= 0.5
    if not melee and unit_set & {"bad shot", "slabo strzela", "zle strzela"}:
        q = 5
    if not melee and unit_set & {"good shot", "dobrze strzela"}:
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
    range_value = normalize_range_value(weapon.range)
    traits = split_traits(weapon.tags)
    attacks_value = weapon.attacks if weapon.attacks is not None else 1.0
    cost = max(
        _weapon_cost(
            unit_quality,
            range_value,
            attacks_value,
            weapon.ap or 0,
            traits,
            unit_traits,
        ),
        0.0,
    )
    return round(cost, 2)


def ability_cost(ability_link: models.UnitAbility, unit_traits: Sequence[str] | None = None) -> float:
    ability = ability_link.ability
    if not ability:
        return 0.0
    if ability.cost_hint is not None:
        return float(ability.cost_hint)
    return ability_cost_from_name(ability.name or "", unit_traits)


def unit_total_cost(unit: models.Unit) -> float:
    flags = parse_flags(unit.flags)
    unit_traits = flags_to_ability_list(flags)
    cost = base_model_cost(unit.quality, unit.defense, unit.toughness, unit_traits)
    if unit.default_weapon:
        cost += weapon_cost(unit.default_weapon, unit.quality, flags)
    cost += sum(ability_cost(link, unit_traits) for link in unit.abilities)
    return round(cost, 2)


def roster_unit_cost(roster_unit: models.RosterUnit) -> float:
    flags = parse_flags(roster_unit.unit.flags)
    unit_traits = flags_to_ability_list(flags)
    unit_cost = base_model_cost(
        roster_unit.unit.quality,
        roster_unit.unit.defense,
        roster_unit.unit.toughness,
        unit_traits,
    )

    weapon = roster_unit.selected_weapon or roster_unit.unit.default_weapon
    if weapon:
        unit_cost += weapon_cost(weapon, roster_unit.unit.quality, flags)

    unit_cost += sum(ability_cost(link, unit_traits) for link in roster_unit.unit.abilities)

    total = unit_cost * max(roster_unit.count, 1)
    if roster_unit.extra_weapons_json:
        total += 5
    return round(total, 2)


def roster_total(roster: models.Roster) -> float:
    return round(sum(roster_unit_cost(ru) for ru in roster.roster_units), 2)


def update_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for ru in roster_units:
        ru.cached_cost = roster_unit_cost(ru)
