"""Moduł kalkulacji kosztów jednostek i broni zgodny z arkuszem VBA."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from .. import models

# --- Stałe tabel z arkusza ---
QUALITY_BASE = {2: 1.2, 3: 1.1, 4: 1.0, 5: 0.9, 6: 0.8}
QUALITY_FEARLESS = {2: 1.25, 3: 1.2, 4: 1.15, 5: 1.1, 6: 1.05}

DEFENSE_TABLE = {
    1: {2: 2.0, 3: 1.67, 4: 1.33, 5: 1.0, 6: 0.8},
    2: {2: 1.95, 3: 1.6, 4: 1.2, 5: 0.9, 6: 0.67},
    3: {2: 2.05, 3: 1.8, 4: 1.5, 5: 1.3, 6: 1.2},
    4: {2: 3.0, 3: 2.3, 4: 1.8, 5: 1.4, 6: 1.2},
}

TOUGHNESS_SPECIAL = {1: 1.0, 2: 2.15, 3: 3.5}

RANGE_MULTIPLIERS = {"0": 0.6, "12": 0.65, "18": 1.0, "24": 1.25, "30": 1.45, "36": 1.55}

AP_BASE = {-1: 0.8, 0: 1.0, 1: 1.5, 2: 1.9, 3: 2.25, 4: 2.5, 5: 2.65}
AP_LANCE = {-1: 0.15, 0: 0.35, 1: 0.3, 2: 0.25, 3: 0.15, 4: 0.1, 5: 0.05}
AP_NO_COVER = {-1: 0.1, 0: 0.25, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.05}
AP_CORROSIVE = {-1: 0.05, 0: 0.05, 1: 0.1, 2: 0.25, 3: 0.4, 4: 0.5, 5: 0.55}

BLAST_MULTIPLIER = {2: 1.95, 3: 2.8, 6: 4.3}
DEADLY_MULTIPLIER = {2: 1.9, 3: 2.6, 6: 3.8}

# --- Zestawy nazw zdolności ---
FEARLESS_SET = {"nieustraszony", "stracency", "fearless", "expendable"}
FRAGILE_SET = {"delikatny", "fragile"}
INVULNERABLE_SET = {"niewrazliwy", "invulnerable", "inv"}
REGEN_SET = {"regeneracja", "regen", "regeneration"}
FURIOUS_SET = {"furia", "furious"}
RELENTLESS_SET = {"nieustepliwy", "relentless"}
WARRIOR_SET = {"wojownik", "wojownicy", "fighter"}
SHOOTER_SET = {"strzelec", "strzelcy", "shooter"}
BAD_SHOT_SET = {
    "bad shot",
    "slabo strzela",
    "slabo strzelaja",
    "zle strzela",
    "zle strzelaja",
    "zle strzelac",
}
GOOD_SHOT_SET = {"good shot", "dobrze strzela", "dobrze strzelaja"}
FLYING_SET = {"latajacy", "latajaca", "lata", "flying"}
FAST_SET = {"szybki", "szybka", "szybcy", "fast"}
AMBUSH_SET = {"zasadzka", "ambush"}
SCOUT_SET = {"zwiadowca", "scout"}
AIRCRAFT_SET = {"samolot", "aircraft"}

WEAPON_TRAIT_SUGGESTIONS = [
    "Szturmowy",
    "Rozprysk(2)",
    "Rozprysk(3)",
    "Rozprysk(6)",
    "Zabójczy(2)",
    "Zabójczy(3)",
    "Zabójczy(6)",
    "Rozrywający",
    "Lanca",
    "Namierzanie",
    "Ciężki",
    "Impet",
    "Bez osłon",
    "Żrący",
    "Niebezpośredni",
    "Zużywalny",
    "Precyzyjny",
    "Niezawodny",
    "Bez regeneracji",
    "Podkręcenie",
]

UNIT_ABILITY_SUGGESTIONS = [
    "Zasadzka",
    "Zwiadowca",
    "Szybki",
    "Wolny",
    "Harcownik",
    "Nieruchomy",
    "Zwinny",
    "Niezgrabny",
    "Latający",
    "Samolot",
    "Kontra",
    "Maskowanie",
    "Okopany",
    "Tarcza",
    "Strażnik",
    "Nieustraszony",
    "Straceńcy",
    "Delikatny",
    "Niewrażliwy",
    "Regeneracja",
    "Furia",
    "Nieustępliwy",
    "Wojownik",
    "Strzelec",
    "Słabo strzela",
    "Dobrze strzela",
]

AURA_BENEFITS = ["Nieustraszony", "Delikatny", "Niewrażliwy", "Regeneracja", "Furia", "Nieustępliwy"]
ORDER_BENEFITS = ["Nieustraszony", "Szybki", "Maskowanie", "Strażnik"]
TRANSPORT_CAPACITY = [2, 4, 6, 10]
MAG_LEVELS = [1, 2, 3]


@dataclass(frozen=True)
class UpgradeOption:
    value: str
    label: str


ABILITY_UPGRADE_OPTIONS: list[UpgradeOption] = []
for size in TRANSPORT_CAPACITY:
    ABILITY_UPGRADE_OPTIONS.append(UpgradeOption(value=f"Transport({size})", label=f"Transport({size})"))
for benefit in AURA_BENEFITS:
    ABILITY_UPGRADE_OPTIONS.append(UpgradeOption(value=f"Aura({benefit})", label=f"Aura({benefit})"))
for level in MAG_LEVELS:
    ABILITY_UPGRADE_OPTIONS.append(UpgradeOption(value=f"Mag({level})", label=f"Mag({level})"))
ABILITY_UPGRADE_OPTIONS.extend(
    [
        UpgradeOption(value="Przekaźnik", label="Przekaźnik"),
        UpgradeOption(value="Łatanie", label="Łatanie"),
        UpgradeOption(value="Radio", label="Radio"),
    ]
)
for benefit in ORDER_BENEFITS:
    ABILITY_UPGRADE_OPTIONS.append(UpgradeOption(value=f"Rozkaz: {benefit}", label=f"Rozkaz: {benefit}"))


# --- Funkcje pomocnicze ---

def _normalize(text: str | None) -> str:
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    cleaned = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return cleaned.lower().strip()


def _extract_number(text: str) -> float:
    match = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", text)
    return float(match.group()) if match else 0.0


def _split_entries(text: str | None) -> list[str]:
    if not text:
        return []
    separators = text.replace(";", ",").replace("\n", ",")
    return [entry.strip() for entry in separators.split(",") if entry.strip()]


def get_known_weapon_tags() -> list[str]:
    return sorted(dict.fromkeys(WEAPON_TRAIT_SUGGESTIONS))


def get_known_unit_abilities() -> list[str]:
    return sorted(dict.fromkeys(UNIT_ABILITY_SUGGESTIONS))


def ability_upgrade_choices() -> list[UpgradeOption]:
    return list(ABILITY_UPGRADE_OPTIONS)


def parse_weapon_tags(text: str | None) -> list[str]:
    return _split_entries(text)


def parse_unit_abilities(text: str | None) -> list[str]:
    return _split_entries(text)


def normalize_range_value(value: str | None) -> str:
    if value is None:
        return "0"
    raw = str(value).strip()
    if not raw:
        return "0"
    lowered = _normalize(raw)
    if lowered in {"0", "melee", "walcz", "walka", "wrecz"}:
        return "0"
    cleaned = raw.replace('"', "").replace("''", "").strip()
    try:
        number = int(float(cleaned))
    except ValueError:
        return raw
    return str(number)


def _quality_modifier(quality: int, row: int) -> float:
    quality = max(2, min(6, int(quality)))
    if row == 2:
        return QUALITY_FEARLESS.get(quality, QUALITY_FEARLESS[4])
    return QUALITY_BASE.get(quality, QUALITY_BASE[4])


def _defense_modifier(defense: int, row: int) -> float:
    defense = max(2, min(6, int(defense)))
    table = DEFENSE_TABLE.get(row, DEFENSE_TABLE[1])
    return table.get(defense, table[4])


def _toughness_modifier(toughness: int) -> float:
    if toughness in TOUGHNESS_SPECIAL:
        return TOUGHNESS_SPECIAL[toughness]
    return max((5 * toughness) // 3 - 2, 1)


def _passive_cost(ability_name: str, toughness: float = 1.0, aura: bool = False) -> float:
    key = _normalize(ability_name)
    cost = 0.0
    if key in {"zasadzka", "ambush"}:
        cost = 2 * toughness
    elif key in {"zwiadowca", "scout"}:
        cost = 2 * toughness
    elif key in {"szybki", "szybka", "szybcy", "fast"}:
        cost = 1 * toughness
    elif key in {"wolny", "slow"}:
        cost = -1 * toughness
    elif key in {"harcownik", "skirmisher"}:
        cost = 1.5 * toughness
    elif key in {"nieruchomy", "immobile"}:
        cost = 2.5 * toughness
    elif key in {"zwinny", "agile"}:
        cost = 0.5 * toughness
    elif key in {"niezgrabny", "clumsy"}:
        cost = -0.5 * toughness
    elif key in FLYING_SET:
        cost = 1 * toughness
    elif key in AIRCRAFT_SET:
        cost = 3 * toughness
    elif key in {"kontra", "counter"}:
        cost = 2 * toughness
    elif key in {"maskowanie", "camouflage", "stealth"}:
        cost = 2 * toughness
    elif key in {"okopany", "fortified", "entrenched"}:
        cost = 1 * toughness
    elif key in {"tarcza", "shield"}:
        cost = 1.25 * toughness
    elif key in {"straznik", "strażnik", "guardian", "overwatch"}:
        cost = 3 * toughness
    else:
        if aura:
            if key in FEARLESS_SET:
                cost = 1.5 * toughness
            elif key in FRAGILE_SET:
                cost = 0.5 * toughness
            elif key in INVULNERABLE_SET:
                cost = 2 * toughness
            elif key in REGEN_SET:
                cost = 3.5 * toughness
            elif key in FURIOUS_SET:
                cost = 3 * toughness
            elif key in RELENTLESS_SET:
                cost = 3.5 * toughness
        if key.startswith("strach") or key.startswith("fear ") or key.startswith("fear("):
            cost = 0.75 * _extract_number(key)
    return cost


def base_model_cost(quality: int, defense: int, toughness: int, abilities: Sequence[str] | None = None) -> float:
    abilities = abilities or []
    qua_row = 1
    def_row = 1
    passive = 0.0
    for ability in abilities:
        normalized = _normalize(ability)
        if normalized in FEARLESS_SET:
            qua_row = 2
        elif normalized in FRAGILE_SET:
            def_row = 2
        elif normalized in INVULNERABLE_SET:
            def_row = 3
        elif normalized in REGEN_SET:
            def_row = 4
        else:
            passive += _passive_cost(normalized, toughness)
    base = 5.0 * _quality_modifier(quality, qua_row) * _defense_modifier(defense, def_row) * _toughness_modifier(toughness)
    return round(base + passive, 2)


def _range_multiplier(range_value: str) -> float:
    if range_value in RANGE_MULTIPLIERS:
        return RANGE_MULTIPLIERS[range_value]
    try:
        distance = int(float(range_value))
    except ValueError:
        return RANGE_MULTIPLIERS["18"]
    best_key = "18"
    best_delta = abs(distance - 18)
    for key in ("12", "18", "24", "30", "36"):
        delta = abs(distance - int(key))
        if delta < best_delta:
            best_key = key
            best_delta = delta
    return RANGE_MULTIPLIERS.get(best_key, RANGE_MULTIPLIERS["18"])


def _weapon_cost_internal(
    quality: int,
    range_value: str,
    attacks: float,
    ap: int,
    weapon_traits: Sequence[str],
    unit_abilities: Sequence[str],
    allow_assault_bonus: bool = True,
) -> float:
    range_key = str(range_value).strip()
    if not range_key:
        range_key = "0"
    normalized_range = _normalize(range_key)
    if normalized_range in {"melee", "walka", "walcz", "wrecz"}:
        range_key = "0"
    else:
        try:
            range_key = str(int(float(range_key)))
        except ValueError:
            range_key = range_key

    q_value = int(quality)
    ap = max(-1, min(5, int(ap)))
    chance = 7.0
    ap_mod = AP_BASE.get(ap, AP_BASE[0])
    mult = 1.0
    assault = False
    overcharge = False

    for ability in unit_abilities:
        normalized = _normalize(ability)
        if normalized in FURIOUS_SET:
            if range_key == "0":
                chance += 0.65
        elif normalized in RELENTLESS_SET:
            if range_key != "0":
                chance += 0.65
        elif normalized in WARRIOR_SET:
            if range_key != "0":
                mult *= 0.5
        elif normalized in SHOOTER_SET:
            if range_key == "0":
                mult *= 0.5
        elif normalized in BAD_SHOT_SET:
            if range_key != "0":
                q_value = 5
        elif normalized in GOOD_SHOT_SET:
            if range_key != "0":
                q_value = 4

    for trait in weapon_traits:
        normalized = _normalize(trait)
        if normalized.startswith("rozprysk") or normalized.startswith("blast"):
            number = int(_extract_number(normalized))
            if number in BLAST_MULTIPLIER:
                mult *= BLAST_MULTIPLIER[number]
            continue
        if normalized.startswith("zabojczy") or normalized.startswith("deadly"):
            number = int(_extract_number(normalized))
            if number in DEADLY_MULTIPLIER:
                mult *= DEADLY_MULTIPLIER[number]
            continue
        if normalized in {"rozrywajacy", "rozrywajaca", "rending"}:
            chance += 1
        elif normalized in {"lanca", "lance"}:
            chance += 0.65
        elif normalized in {"namierzanie", "lock-on", "lock on"}:
            chance += 0.35
            mult *= 1.1
            ap_mod += AP_NO_COVER[ap]
        elif normalized in {"ciezki", "ciezka", "heavy"}:
            chance -= 0.35
        elif normalized in {"impet", "impact"}:
            ap_mod += AP_LANCE[ap]
        elif normalized in {"bez oslony", "bez oslon", "no cover"}:
            ap_mod += AP_NO_COVER[ap]
        elif normalized in {"zracy", "zrazy", "zraca", "zrace", "corrosive"}:
            ap_mod += AP_CORROSIVE[ap]
        elif normalized in {"niebezposredni", "indirect"}:
            mult *= 1.2
        elif normalized in {"zuzywalny", "zuzywalna", "limited"}:
            mult *= 0.5
        elif normalized in {"precyzyjny", "precyzyjna", "precise"}:
            mult *= 1.5
        elif normalized in {"niezawodny", "niezawodna", "reliable"}:
            q_value = 2
        elif normalized in {"szturmowy", "szturmowa", "assault"}:
            assault = True
        elif normalized in {"bez regeneracji", "bez regegenracji", "no regen", "no regeneration"}:
            mult *= 1.1
        elif normalized in {"podkrecenie", "podkrecanie", "podkrecone", "overcharge", "overclock"}:
            overcharge = True

    range_multiplier = _range_multiplier(range_key)
    chance = max(chance - q_value, 1.0)
    cost = float(attacks) * 2 * range_multiplier * ap_mod * mult * chance

    if overcharge and (not assault or range_key != "0"):
        cost *= 1.4

    if assault and range_key != "0" and allow_assault_bonus:
        melee_cost = _weapon_cost_internal(
            quality,
            "0",
            attacks,
            ap,
            weapon_traits,
            unit_abilities,
            allow_assault_bonus=False,
        )
        cost += melee_cost

    return cost


def weapon_cost(
    weapon: models.Weapon | None,
    quality: int,
    unit_abilities: Sequence[str] | None = None,
) -> float:
    if weapon is None:
        return 0.0
    range_value = normalize_range_value(weapon.range)
    traits = parse_weapon_tags(weapon.tags)
    unit_abilities = unit_abilities or []
    cost = _weapon_cost_internal(quality, range_value, weapon.attacks or 1, weapon.ap or 0, traits, unit_abilities)
    return round(cost, 2)


def _ability_cost_internal(name: str, unit_abilities: Sequence[str], toughness: int) -> float:
    desc = _normalize(name)
    raw = (name or "").strip().lower()
    cost = 0.0
    if desc.startswith("transport"):
        capacity = _extract_number(desc)
        mult = 1.0
        for ability in unit_abilities:
            normalized = _normalize(ability)
            if normalized in AIRCRAFT_SET:
                mult = 3.5
            elif normalized in AMBUSH_SET or normalized in SCOUT_SET:
                mult = 2.5
            elif normalized in FLYING_SET:
                mult = 1.5
            elif normalized in FAST_SET:
                mult = 1.25
        cost = capacity * mult
    elif desc.startswith("aura"):
        aura_range = 0.0
        ability_name = desc[4:].strip()
        if ability_name.startswith("("):
            closing = ability_name.find(")")
            if closing != -1:
                aura_range = _extract_number(ability_name[: closing + 1])
                ability_name = ability_name[closing + 1 :].strip(" :")
        elif ability_name.startswith(":"):
            ability_name = ability_name[1:].strip()
        cost = _passive_cost(ability_name, 8, True)
        if aura_range == 12:
            cost *= 2
    elif desc.startswith("mag"):
        level = _extract_number(desc)
        cost = 8 * level
    elif desc in {"przekaznik", "relay"} or raw in {"przekaźnik"}:
        cost = 4
    elif desc in {"latanie", "patching", "repair"} or raw in {"łatanie"}:
        cost = 20
    elif desc.startswith("rozkaz") or desc.startswith("order"):
        ability_name = desc.split(":", 1)[1].strip() if ":" in desc else desc[6:].strip()
        cost = _passive_cost(ability_name, 10, True)
    elif desc in {"radio", "vox"}:
        cost = 3
    return cost


def ability_upgrade_cost(name: str, unit_abilities: Sequence[str] | None, toughness: int) -> float:
    abilities = unit_abilities or []
    cost = _ability_cost_internal(name, abilities, toughness)
    return round(cost, 2)


def ability_cost(link: models.UnitAbility) -> float:
    if link.ability and link.ability.cost_hint is not None:
        return float(link.ability.cost_hint)
    return 0.0


def unit_total_cost(unit: models.Unit) -> float:
    abilities = parse_unit_abilities(unit.flags)
    cost = base_model_cost(unit.quality, unit.defense, unit.toughness, abilities)
    if unit.default_weapon:
        cost += weapon_cost(unit.default_weapon, unit.quality, abilities)
    cost += sum(ability_cost(link) for link in unit.abilities)
    return round(cost, 2)


def _load_upgrades(roster_unit: models.RosterUnit) -> dict:
    if not roster_unit.extra_weapons_json:
        return {"weapon_upgrades": [], "ability_upgrades": []}
    try:
        data = json.loads(roster_unit.extra_weapons_json)
    except (TypeError, json.JSONDecodeError):
        return {"weapon_upgrades": [], "ability_upgrades": []}
    data.setdefault("weapon_upgrades", [])
    data.setdefault("ability_upgrades", [])
    return data


def roster_unit_cost(roster_unit: models.RosterUnit) -> float:
    unit = roster_unit.unit
    abilities = parse_unit_abilities(unit.flags)
    base_model = base_model_cost(unit.quality, unit.defense, unit.toughness, abilities)
    base_weapon = roster_unit.selected_weapon or unit.default_weapon
    weapon_value = weapon_cost(base_weapon, unit.quality, abilities)
    ability_value = sum(ability_cost(link) for link in unit.abilities)
    per_model = base_model + weapon_value + ability_value
    total = per_model * max(roster_unit.count, 1)
    upgrades = _load_upgrades(roster_unit)
    for entry in upgrades.get("weapon_upgrades", []):
        total += float(entry.get("delta", 0))
    for entry in upgrades.get("ability_upgrades", []):
        total += float(entry.get("delta", 0))
    return round(total, 2)


def roster_total(roster: models.Roster) -> float:
    return round(sum(roster_unit_cost(ru) for ru in roster.roster_units), 2)


def update_cached_costs(roster_units: Iterable[models.RosterUnit]) -> None:
    for roster_unit in roster_units:
        roster_unit.cached_cost = roster_unit_cost(roster_unit)


def per_model_weapon_delta(
    unit: models.Unit,
    base_weapon: models.Weapon | None,
    new_weapon: models.Weapon,
) -> float:
    abilities = parse_unit_abilities(unit.flags)
    base_value = weapon_cost(base_weapon, unit.quality, abilities) if base_weapon else 0.0
    new_value = weapon_cost(new_weapon, unit.quality, abilities)
    return round(new_value - base_value, 2)


def per_model_ability_delta(unit: models.Unit, ability_name: str) -> float:
    abilities = parse_unit_abilities(unit.flags)
    return ability_upgrade_cost(ability_name, abilities, unit.toughness)
