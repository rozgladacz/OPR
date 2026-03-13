from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"


def _run_compute_total_cost_cases(cases: list[dict[str, object]]) -> dict[str, float]:
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
        const output = {{}};
        for (const testCase of cases) {{
          const state = {{
            mode: testCase.mode,
            weapons: new Map(Object.entries(testCase.weapons || {{}}).map(([k, v]) => [Number(k), Number(v)])),
            active: new Map(Object.entries(testCase.active || {{}}).map(([k, v]) => [String(k), Number(v)])),
            aura: new Map(),
            passive: new Map(Object.entries(testCase.passive || {{}}).map(([k, v]) => [String(k), Number(v)])),
            activeLabels: new Map(),
            auraLabels: new Map(),
          }};
          const total = sandbox.computeTotalCost(
            testCase.basePerModel,
            testCase.modelCount,
            testCase.weaponOptions,
            state,
            {{
              active: new Map(Object.entries(testCase.activeCosts || {{}})),
              passive: new Map(Object.entries(testCase.passiveCosts || {{}})),
            }},
            testCase.passiveItems,
            null,
          );
          output[testCase.name] = total;
        }}
        console.log(JSON.stringify(output));
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_compute_total_cost_massive_and_non_massive_modes_regression() -> None:
    base_case = {
        "basePerModel": 10,
        "modelCount": 3,
        "weaponOptions": [{"id": 1, "cost": 5}],
        "weapons": {"1": 2},
        "active": {"101": 1},
        "activeCosts": {"101": 7},
        "passive": {"extra": 1},
        "passiveCosts": {"extra": 11},
    }
    cases = [
        {
            **base_case,
            "name": "massive_per_model",
            "mode": "per_model",
            "passiveItems": [
                {"slug": "masywny", "default_count": 1, "cost": 0},
                {"slug": "extra", "default_count": 0, "cost": 11},
            ],
        },
        {
            **base_case,
            "name": "massive_total",
            "mode": "total",
            "passiveItems": [
                {"slug": "masywny", "default_count": 1, "cost": 0},
                {"slug": "extra", "default_count": 0, "cost": 11},
            ],
        },
        {
            **base_case,
            "name": "regular_per_model",
            "mode": "per_model",
            "passiveItems": [
                {"slug": "extra", "default_count": 0, "cost": 11},
            ],
        },
        {
            **base_case,
            "name": "regular_total",
            "mode": "total",
            "passiveItems": [
                {"slug": "extra", "default_count": 0, "cost": 11},
            ],
        },
    ]

    totals = _run_compute_total_cost_cases(cases)

    assert totals["massive_per_model"] == 78
    assert totals["massive_total"] == 58
    assert totals["regular_per_model"] == 114
    assert totals["regular_total"] == 58
