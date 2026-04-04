from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import costs
from app.services.costs import _weapon_cost
from tests.node_runtime import resolve_node_binary

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"
NUMERIC_TOLERANCE = 1e-6
LEGACY_PARITY_ENABLED = os.getenv("ENABLE_LEGACY_MATH_PARITY_TESTS", "").strip() in {
    "1",
    "true",
    "yes",
}
pytestmark = pytest.mark.skipif(
    not LEGACY_PARITY_ENABLED,
    reason="legacy frontend-backend math parity test (planned for removal)",
)

SCENARIOS: list[dict[str, object]] = [
    {
        "name": "ap_base_only",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 2,
        "weapon_traits": [],
        "unit_traits": [],
    },
    {
        "name": "limited",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Limited"],
        "unit_traits": [],
    },
    {
        "name": "blast_and_deadly",
        "quality": 4,
        "range": 18,
        "attacks": 3,
        "ap": 1,
        "weapon_traits": ["Blast(3)", "Deadly(2)"],
        "unit_traits": [],
    },
    {
        "name": "overcharge_only",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 2,
        "weapon_traits": ["Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "assault_plus_overcharge",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 2,
        "weapon_traits": ["Assault", "Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "penetrating_and_brutal",
        "quality": 3,
        "range": 0,
        "attacks": 4,
        "ap": 2,
        "weapon_traits": ["Penetrating", "Brutalny"],
        "unit_traits": ["Furia"],
    },
    {
        "name": "artillery_and_unwieldy",
        "quality": 4,
        "range": 30,
        "attacks": 1.5,
        "ap": 0,
        "weapon_traits": ["Artyleria", "Nieporeczny"],
        "unit_traits": ["Ostrozny"],
    },
]


def _run_frontend_cases(scenarios: list[dict[str, object]]) -> dict[str, float]:
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

        const scenarios = {json.dumps(scenarios)};
        const output = {{}};
        for (const scenario of scenarios) {{
          output[scenario.name] = sandbox.weaponCostInternal(
            scenario.quality,
            scenario.range,
            scenario.attacks,
            scenario.ap,
            scenario.weapon_traits,
            scenario.unit_traits,
            true,
          );
        }}
        console.log(JSON.stringify(output));
        """
    )
    completed = subprocess.run([resolve_node_binary(), "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_weapon_cost_python_node_sandbox_parity() -> None:
    frontend = _run_frontend_cases(SCENARIOS)

    for scenario in SCENARIOS:
        backend = _weapon_cost(
            int(scenario["quality"]),
            int(scenario["range"]),
            float(scenario["attacks"]),
            int(scenario["ap"]),
            list(scenario["weapon_traits"]),
            list(scenario["unit_traits"]),
            allow_assault_extra=True,
        )
        assert frontend[scenario["name"]] == pytest.approx(backend, abs=NUMERIC_TOLERANCE), scenario["name"]


E2E_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "e2e_melee",
        "quality": 4,
        "range": 0,
        "attacks": 3,
        "ap": 2,
        "weapon_traits": ["Brutalny"],
        "unit_traits": ["wojownik"],
    },
    {
        "name": "e2e_ranged",
        "quality": 4,
        "range": 30,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Artyleria"],
        "unit_traits": ["strzelec"],
    },
    {
        "name": "e2e_mixed_assault",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault", "Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "e2e_trait_warrior",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Deadly(2)"],
        "unit_traits": ["wojownik"],
    },
    {
        "name": "e2e_trait_shooter",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault"],
        "unit_traits": ["strzelec"],
    },
]


def _selected_total_for_slug(melee: float, ranged: float, slug: str) -> float:
    if slug == "wojownik":
        return round(melee + ranged * 0.5, 2)
    return round(ranged + melee * 0.5, 2)


def _backend_projection(case: dict[str, Any], *, previous_slug: str | None = None) -> dict[str, Any]:
    weapon = SimpleNamespace(
        effective_range=case["range"],
        effective_attacks=case["attacks"],
        effective_ap=case["ap"],
        effective_tags=", ".join(case["weapon_traits"]),
        effective_cached_cost=None,
    )
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


def _run_frontend_e2e_cases(
    scenarios: list[dict[str, Any]],
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

        const scenarios = {json.dumps(scenarios)};
        const previousSlug = {json.dumps(previous_slug)};
        const classify = (melee, ranged, fallbackSlug) => {{
          if (melee > ranged) return {{ slug: 'wojownik' }};
          if (ranged > melee) return {{ slug: 'strzelec' }};
          const fallback = fallbackSlug === 'strzelec' ? 'strzelec' : 'wojownik';
          return {{ slug: fallback }};
        }};
        const output = {{}};
        for (const scenario of scenarios) {{
          const components = sandbox.weaponCostComponentsInternal(
            scenario.quality,
            scenario.range,
            scenario.attacks,
            scenario.ap,
            scenario.weapon_traits,
            scenario.unit_traits,
          );
          const classification = classify(components.melee, components.ranged, previousSlug);
          const slug = classification ? classification.slug : null;
          const totalCost = slug === 'wojownik'
            ? Math.round((components.melee + components.ranged * 0.5) * 100) / 100
            : Math.round((components.ranged + components.melee * 0.5) * 100) / 100;
          output[scenario.name] = {{
            classification: slug,
            melee: components.melee,
            ranged: components.ranged,
            total_cost: totalCost,
          }};
        }}
        console.log(JSON.stringify(output));
        """
    )
    completed = subprocess.run([resolve_node_binary(), "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_weapon_cost_end_to_end_projection_sandbox_matches_backend() -> None:
    frontend = _run_frontend_e2e_cases(E2E_SCENARIOS)

    for scenario in E2E_SCENARIOS:
        backend = _backend_projection(scenario)
        current = frontend[scenario["name"]]
        assert current["classification"] == backend["classification"], scenario["name"]
        assert current["melee"] == pytest.approx(backend["melee"], abs=NUMERIC_TOLERANCE), scenario["name"]
        assert current["ranged"] == pytest.approx(backend["ranged"], abs=NUMERIC_TOLERANCE), scenario["name"]
        assert current["total_cost"] == pytest.approx(backend["total_cost"], abs=NUMERIC_TOLERANCE), scenario["name"]


def test_weapon_cost_end_to_end_tie_break_sandbox_matches_backend_fallback() -> None:
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

    frontend = _run_frontend_e2e_cases(tie_case, previous_slug="strzelec")
    backend = _backend_projection(tie_case[0], previous_slug="strzelec")
    current = frontend["e2e_tie_assault"]

    assert current["melee"] == pytest.approx(current["ranged"], abs=NUMERIC_TOLERANCE)
    assert current["classification"] == "strzelec"
    assert current["classification"] == backend["classification"]
    assert current["total_cost"] == pytest.approx(backend["total_cost"], abs=NUMERIC_TOLERANCE)

