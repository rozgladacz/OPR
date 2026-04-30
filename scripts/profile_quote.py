"""Profile calculate_roster_unit_quote across every unit in a roster.

Usage:
    python scripts/profile_quote.py [ROSTER_ID]
    make profile ROSTER=10

Prints per-unit timings (include_item_costs=True/False) plus a cProfile
top-25 dump for the slowest unit.  Used to verify performance changes in
``app/services/costs.py`` against the baseline in ``docs/PERFORMANCE.md``.

The script forces UTF-8 stdout because it prints ASCII-art arrows and
project unit names contain Polish characters; on Windows the default
``cp1250`` console codec crashes mid-run otherwise.
"""

from __future__ import annotations

import cProfile
import io
import os
import pathlib
import pstats
import sys
import time

# Ensure UTF-8 stdout regardless of console codec (Windows cp1250 etc.).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Make `import app.*` work whether the script is invoked via
# `python scripts/profile_quote.py`, `make profile`, or from a sibling dir.
_repo_root = pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Initialise the FastAPI app first to avoid SessionLocal circular-import issues.
import app.main  # noqa: F401  pylint: disable=unused-import

from sqlalchemy.orm import selectinload

from app import models
from app.db import SessionLocal
from app.services.costs import (
    ability_identifier,
    calculate_roster_unit_quote,
    normalize_name,
)


def profile_roster(roster_id: int, *, runs: int = 3, profile_runs: int = 1) -> None:
    # Reset LRU caches so the first timed call pays cold-cache cost.
    ability_identifier.cache_clear()
    normalize_name.cache_clear()

    session = SessionLocal()
    try:
        roster = (
            session.query(models.Roster)
            .options(
                selectinload(models.Roster.roster_units)
                .selectinload(models.RosterUnit.unit)
                .selectinload(models.Unit.weapon_links)
                .selectinload(models.UnitWeapon.weapon),
                selectinload(models.Roster.roster_units)
                .selectinload(models.RosterUnit.unit)
                .selectinload(models.Unit.abilities)
                .selectinload(models.UnitAbility.ability),
                selectinload(models.Roster.roster_units)
                .selectinload(models.RosterUnit.unit)
                .selectinload(models.Unit.default_weapon),
            )
            .filter(models.Roster.id == roster_id)
            .one_or_none()
        )
        if roster is None:
            print(f"Roster {roster_id} not found.")
            sys.exit(1)

        units = [ru for ru in roster.roster_units if ru.unit is not None]
        print(f"Roster {roster_id}: {len(units)} units")
        print()
        print(
            f"{'ru':>4}  {'name':<25}  {'wpns':>4} {'abil':>4}  "
            f"{'full(ms)':>8}  {'badge(ms)':>9}"
        )
        print("-" * 64)

        full_total = 0.0
        badge_total = 0.0
        worst = (None, 0.0)

        for ru in units:
            unit = ru.unit
            loadout = ru.extra_weapons_json or {}
            count = ru.count or 1

            # Warm-up
            calculate_roster_unit_quote(unit, loadout, count, include_item_costs=True)

            # full breakdown
            t0 = time.perf_counter()
            for _ in range(runs):
                calculate_roster_unit_quote(unit, loadout, count, include_item_costs=True)
            full_ms = (time.perf_counter() - t0) / runs * 1000
            full_total += full_ms

            # badge-only
            t0 = time.perf_counter()
            for _ in range(runs):
                calculate_roster_unit_quote(unit, loadout, count, include_item_costs=False)
            badge_ms = (time.perf_counter() - t0) / runs * 1000
            badge_total += badge_ms

            n_weapons = len(getattr(unit, "weapon_links", []) or [])
            n_abilities = len(getattr(unit, "abilities", []) or [])
            short_name = (unit.name or "")[:25]
            print(
                f"{ru.id:>4}  {short_name:<25}  {n_weapons:>4} {n_abilities:>4}  "
                f"{full_ms:>8.1f}  {badge_ms:>9.1f}"
            )

            if full_ms > worst[1]:
                worst = (ru, full_ms)

        print("-" * 64)
        print(
            f"{'TOTAL':>4}  {'':<25}  {'':>4} {'':>4}  "
            f"{full_total:>8.1f}  {badge_total:>9.1f}"
        )

        if worst[0] is None or profile_runs <= 0:
            return

        worst_ru = worst[0]
        worst_unit = worst_ru.unit
        worst_loadout = worst_ru.extra_weapons_json or {}
        worst_count = worst_ru.count or 1

        print()
        print(f"--- cProfile top 25 (worst unit: ru {worst_ru.id} '{worst_unit.name}') ---")
        prof = cProfile.Profile()
        prof.enable()
        for _ in range(profile_runs):
            calculate_roster_unit_quote(
                worst_unit, worst_loadout, worst_count, include_item_costs=True
            )
        prof.disable()
        buf = io.StringIO()
        pstats.Stats(prof, stream=buf).sort_stats("cumulative").print_stats(25)
        print(buf.getvalue())
    finally:
        session.close()


def main() -> None:
    roster_id = 10
    if len(sys.argv) >= 2:
        try:
            roster_id = int(sys.argv[1])
        except ValueError:
            print(f"Invalid roster id: {sys.argv[1]!r}")
            sys.exit(2)
    profile_roster(roster_id)


if __name__ == "__main__":
    main()
