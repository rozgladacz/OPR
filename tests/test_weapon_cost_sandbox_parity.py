from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.services.costs import _weapon_cost

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
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
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
