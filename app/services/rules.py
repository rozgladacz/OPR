
from typing import List
from dataclasses import dataclass

# NOTE: This module is intentionally standalone and side-effect free.
# It exposes a single function: collect_roster_warnings(roster) -> List[str].
# Import in routers/rosters.py and include its output in the Jinja context.

@dataclass
class UnitSummary:
    name: str
    models: int
    is_hero: bool = False
    has_active: int = 0
    has_aura: bool = False
    total_cost: int = 0

def _flatten_units(roster) -> list:
    # minimal, duck-typed: works if roster has .items with .unit/.models/.total_cost and unit has .name, .abilities etc.
    units = []
    try:
        for item in getattr(roster, "items", []):
            u = getattr(item, "unit", None)
            if u is None:
                # some repos name relation differently
                u = getattr(item, "template_unit", None)
            name = getattr(u, "name", "UNIT")
            models = getattr(item, "models", 1)
            total_cost = int(getattr(item, "total_cost", 0))
            # abilities can be list of strings or objects with .name and flags
            abilities = getattr(u, "abilities", []) or []
            # fallbacks for active/aura/hero flags
            is_hero = any(getattr(a, "code", getattr(a, "name", "")).lower() in ("bohater","hero") for a in abilities)                           or getattr(u, "is_hero", False)
            has_active_cnt = sum(1 for a in abilities if getattr(a, "kind", "").lower() == "active" or "mag(" in str(getattr(a,"name","")).lower())
            has_aura = any(getattr(a, "kind", "").lower() == "aura" or "aura" in str(getattr(a,"name","")).lower() for a in abilities)
            units.append(UnitSummary(name=name, models=models, is_hero=is_hero, has_active=has_active_cnt, has_aura=has_aura, total_cost=total_cost))
    except Exception:
        # best-effort: return empty -> no warnings
        return []
    return units

def collect_roster_warnings(roster) -> List[str]:
    warnings: List[str] = []
    try:
        total = int(getattr(roster, "total_points", 0) or getattr(roster, "total_cost", 0) or 0)
    except Exception:
        total = 0
    units = _flatten_units(roster)
    # [ACTIVE] more than 1 active per unit
    for u in units:
        if u.has_active > 1:
            warnings.append(f"[ACTIVE] Jednostka '{u.name}' ma >1 zdolność aktywną.")
        if u.has_active >= 1 and u.has_aura:
            warnings.append(f"[AURA] Jednostka '{u.name}' ma jednocześnie aurę i zdolność aktywną.")
        if u.models > 21:
            warnings.append(f"[SIZE] Jednostka '{u.name}' ma {u.models} modeli (>21).")
    # [HERO] max 1/500 pts (soft)
    if total > 0:
        heroes = sum(1 for u in units if u.is_hero)
        allowed = max(1, total // 500)
        if heroes > allowed:
            warnings.append(f"[HERO] Bohaterów {heroes}, standard: ≤ {allowed} (1/500 pkt).")
    # [LIMIT] oddział >35% lub <50 pkt (soft)
    if total > 0:
        for u in units:
            share = (u.total_cost / total) if total else 0
            if share > 0.35:
                warnings.append(f"[LIMIT] '{u.name}' kosztuje {u.total_cost} pkt (>35% całości).")
            if u.total_cost < 50:
                warnings.append(f"[LIMIT] '{u.name}' kosztuje {u.total_cost} pkt (<50 pkt).")
    # Potential future: verify "warrior/shooter" classification cost halving — leave as informational
    warnings.append("[WEAPON MIX] Sprawdź klasyfikację "wojownik/strzelec" (tańsza kategoria ×0.5).")
    return warnings
