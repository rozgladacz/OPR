from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs
from tests.node_runtime import resolve_node_binary

APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"
NUMERIC_TOLERANCE = 0.02


CASES = [
    {
        "name": "bazowa_bron",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 0,
        "weapon_traits": [],
        "unit_traits": [],
    },
    {
        "name": "ap_ge_1",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 2,
        "weapon_traits": [],
        "unit_traits": [],
    },
    {
        "name": "overcharge",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "assault_plus_overcharge",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault", "Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "brutalny",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 2,
        "weapon_traits": ["Brutalny"],
        "unit_traits": [],
    },
    {
        "name": "zasadzka",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": [],
        "unit_traits": ["Zasadzka"],
    },
    {
        "name": "artyleria",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Artyleria"],
        "unit_traits": [],
    },
    {
        "name": "nieporeczny",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Nieporęczny"],
        "unit_traits": [],
    },
    {
        "name": "porazenie_melee",
        "quality": 4,
        "range": 0,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Porażenie"],
        "unit_traits": [],
    },
]


def _run_node_cases(cases: list[dict[str, object]]) -> dict[str, float]:
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({json.dumps(str(APP_JS_PATH))}, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{ setTimeout, clearTimeout }},
          document: {{ addEventListener: () => {{}} }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const cases = {json.dumps(cases)};
        const result = {{}};
        for (const entry of cases) {{
          result[entry.name] = sandbox.weaponCostInternal(
            entry.quality,
            entry.range,
            entry.attacks,
            entry.ap,
            entry.weapon_traits,
            entry.unit_traits,
            true,
          );
        }}
        console.log(JSON.stringify(result));
        """
    )
    completed = subprocess.run([resolve_node_binary(), "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _build_weapon(case: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        effective_range=case["range"],
        effective_attacks=case["attacks"],
        effective_ap=case["ap"],
        effective_tags=", ".join(case["weapon_traits"]),
        effective_cached_cost=None,
    )


def test_frontend_weapon_cost_matches_backend_weapon_cost_with_tolerance() -> None:
    frontend = _run_node_cases(CASES)

    for case in CASES:
        weapon = _build_weapon(case)
        backend = costs.weapon_cost(
            weapon,
            unit_quality=int(case["quality"]),
            unit_flags=list(case["unit_traits"]),
            use_cached=False,
        )
        assert frontend[case["name"]] == pytest.approx(backend, abs=NUMERIC_TOLERANCE)


def test_frontend_alias_ability_identifier_and_cost_match_backend() -> None:
    alias = "Nieustępliwy"
    canonical = "Przygotowanie"
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({json.dumps(str(APP_JS_PATH))}, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{ setTimeout, clearTimeout }},
          document: {{ addEventListener: () => {{}} }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const payload = {{
          aliasIdentifier: sandbox.abilityIdentifier({json.dumps(alias)}),
          canonicalIdentifier: sandbox.abilityIdentifier({json.dumps(canonical)}),
          aliasCost: sandbox.weaponCostInternal(4, 24, 2, 1, [], [{json.dumps(alias)}], true),
          canonicalCost: sandbox.weaponCostInternal(4, 24, 2, 1, [], [{json.dumps(canonical)}], true),
        }};
        console.log(JSON.stringify(payload));
        """
    )
    frontend = json.loads(subprocess.run([resolve_node_binary(), "-e", script], check=True, capture_output=True, text=True).stdout)

    backend_alias_identifier = costs.ability_identifier(alias)
    backend_canonical_identifier = costs.ability_identifier(canonical)
    backend_alias_cost = costs.weapon_cost(
        _build_weapon({"range": 24, "attacks": 2, "ap": 1, "weapon_traits": []}),
        unit_quality=4,
        unit_flags=[alias],
        use_cached=False,
    )
    backend_canonical_cost = costs.weapon_cost(
        _build_weapon({"range": 24, "attacks": 2, "ap": 1, "weapon_traits": []}),
        unit_quality=4,
        unit_flags=[canonical],
        use_cached=False,
    )

    assert frontend["aliasIdentifier"] == backend_alias_identifier
    assert frontend["canonicalIdentifier"] == backend_canonical_identifier
    assert frontend["aliasIdentifier"] == frontend["canonicalIdentifier"]
    assert frontend["aliasCost"] == pytest.approx(backend_alias_cost, abs=NUMERIC_TOLERANCE)
    assert frontend["canonicalCost"] == pytest.approx(backend_canonical_cost, abs=NUMERIC_TOLERANCE)
    assert frontend["aliasCost"] == pytest.approx(frontend["canonicalCost"], abs=NUMERIC_TOLERANCE)


E2E_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "e2e_czysto_melee",
        "quality": 4,
        "range": 0,
        "attacks": 3,
        "ap": 2,
        "weapon_traits": ["Brutalny"],
        "unit_traits": ["Wojownik"],
    },
    {
        "name": "e2e_czysto_ranged",
        "quality": 4,
        "range": 30,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Artyleria"],
        "unit_traits": ["Strzelec"],
    },
    {
        "name": "e2e_mieszane_assault",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault", "Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "e2e_mieszane_wojownik",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Deadly(2)"],
        "unit_traits": ["Wojownik"],
    },
    {
        "name": "e2e_mieszane_strzelec",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault"],
        "unit_traits": ["Strzelec"],
    },
]


def _selected_total_for_slug(melee: float, ranged: float, slug: str) -> float:
    if slug == "wojownik":
        return round(melee + ranged * 0.5, 2)
    return round(ranged + melee * 0.5, 2)


def _backend_projection(case: dict[str, Any], *, previous_slug: str | None = None) -> dict[str, Any]:
    weapon = _build_weapon(case)
    components = costs.weapon_cost_components(
        weapon,
        unit_quality=int(case["quality"]),
        unit_flags=list(case["unit_traits"]),
    )
    classification = costs._roster_unit_classification(
        float(components["melee"]),
        float(components["ranged"]),
        fallback=previous_slug or "wojownik",
    )
    return {
        "classification": classification,
        "melee": float(components["melee"]),
        "ranged": float(components["ranged"]),
        "total_cost": _selected_total_for_slug(
            float(components["melee"]),
            float(components["ranged"]),
            classification,
        ),
    }


def _run_node_e2e_projection(
    cases: list[dict[str, Any]],
    *,
    previous_slug: str | None = None,
) -> dict[str, dict[str, Any]]:
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({json.dumps(str(APP_JS_PATH))}, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{ setTimeout, clearTimeout }},
          document: {{ addEventListener: () => {{}} }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const cases = {json.dumps(cases)};
        const previousSlug = {json.dumps(previous_slug)};
        const classify = (melee, ranged, fallbackSlug) => {{
          if (melee > ranged) return {{ slug: 'wojownik' }};
          if (ranged > melee) return {{ slug: 'strzelec' }};
          const fallback = fallbackSlug === 'strzelec' ? 'strzelec' : 'wojownik';
          return {{ slug: fallback }};
        }};
        const result = {{}};
        for (const entry of cases) {{
          const components = sandbox.weaponCostComponentsInternal(
            entry.quality,
            entry.range,
            entry.attacks,
            entry.ap,
            entry.weapon_traits,
            entry.unit_traits,
          );
          const classification = classify(components.melee, components.ranged, previousSlug);
          const slug = classification ? classification.slug : null;
          const totalCost = slug === 'wojownik'
            ? Math.round((components.melee + components.ranged * 0.5) * 100) / 100
            : Math.round((components.ranged + components.melee * 0.5) * 100) / 100;
          result[entry.name] = {{
            classification: slug,
            melee: components.melee,
            ranged: components.ranged,
            total_cost: totalCost,
          }};
        }}
        console.log(JSON.stringify(result));
        """
    )
    completed = subprocess.run([resolve_node_binary(), "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_frontend_weapon_cost_end_to_end_projection_matches_backend() -> None:
    frontend = _run_node_e2e_projection(E2E_SCENARIOS)

    for case in E2E_SCENARIOS:
        backend = _backend_projection(case)
        current = frontend[case["name"]]
        assert current["classification"] == backend["classification"], case["name"]
        assert current["melee"] == pytest.approx(backend["melee"], abs=NUMERIC_TOLERANCE), case["name"]
        assert current["ranged"] == pytest.approx(backend["ranged"], abs=NUMERIC_TOLERANCE), case["name"]
        assert current["total_cost"] == pytest.approx(backend["total_cost"], abs=NUMERIC_TOLERANCE), case["name"]


def test_frontend_weapon_cost_end_to_end_tie_break_uses_same_fallback_as_backend() -> None:
    tie_case = [
        {
            "name": "e2e_tie_assault",
            "quality": 4,
            "range": 18,
            "attacks": 2,
            "ap": 1,
            "weapon_traits": ["Assault"],
            "unit_traits": [],
        }
    ]
    frontend = _run_node_e2e_projection(tie_case, previous_slug="strzelec")
    backend = _backend_projection(tie_case[0], previous_slug="strzelec")
    entry = frontend["e2e_tie_assault"]

    assert entry["classification"] == "strzelec"
    assert entry["classification"] == backend["classification"]
    assert entry["total_cost"] == pytest.approx(backend["total_cost"], abs=NUMERIC_TOLERANCE)

