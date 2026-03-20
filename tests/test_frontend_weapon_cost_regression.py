from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs

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
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
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
