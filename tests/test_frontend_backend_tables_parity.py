from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs

APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"


def _run_node_payload(
    ap_values: list[int], trait_cases: dict[str, dict[str, object]] | None = None
) -> dict[str, object]:
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

        const payload = vm.runInContext(`(() => {{
          const apValues = {json.dumps(ap_values)};
          const traitCases = {json.dumps(trait_cases or {})};
          const traitMap = {{}};
          Object.entries(traitCases).forEach(([name, flags]) => {{
            traitMap[name] = flagsToAbilityList(flags);
          }});
          return {{
            tables: {{
              AP_BASE,
              AP_LANCE,
              BLAST_MULTIPLIER,
              DEADLY_MULTIPLIER,
              BRUTAL_MULTIPLIER,
            }},
            traitMap,
            apLookups: apValues.map((ap) => ({{
              ap,
              base: lookupWithNearest(AP_BASE, ap),
              lance: lookupWithNearest(AP_LANCE, ap),
              brutal: BRUTAL_MULTIPLIER,
            }})),
          }};
        }})()`, sandbox);
        console.log(JSON.stringify(payload));
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _normalize_table(raw: dict[str, float]) -> dict[int, float]:
    return {int(key): float(value) for key, value in raw.items()}


def test_frontend_tables_match_backend_1_to_1() -> None:
    frontend = _run_node_payload(ap_values=[])["tables"]
    assert _normalize_table(frontend["AP_BASE"]) == pytest.approx(costs.AP_BASE)
    assert _normalize_table(frontend["AP_LANCE"]) == pytest.approx(costs.AP_LANCE)
    assert float(frontend["BRUTAL_MULTIPLIER"]) == pytest.approx(costs.BRUTAL_MULTIPLIER)
    assert _normalize_table(frontend["BLAST_MULTIPLIER"]) == pytest.approx(costs.BLAST_MULTIPLIER)
    assert _normalize_table(frontend["DEADLY_MULTIPLIER"]) == pytest.approx(costs.DEADLY_MULTIPLIER)


@pytest.mark.parametrize("ap_value", [-1, 0, 1, 2, 3, 4, 5])
def test_frontend_backend_ap_lookup_matches_for_selected_combinations(ap_value: int) -> None:
    frontend = _run_node_payload(ap_values=[ap_value])["apLookups"][0]
    assert frontend["base"] == pytest.approx(costs.lookup_with_nearest(costs.AP_BASE, ap_value))
    assert frontend["lance"] == pytest.approx(costs.lookup_with_nearest(costs.AP_LANCE, ap_value))
    assert frontend["brutal"] == pytest.approx(costs.BRUTAL_MULTIPLIER)


def test_frontend_backend_trait_map_match_for_optional_flags() -> None:
    cases = {
        "optional_true_ignored": {"Ambush?": True, "Furia!": True},
        "optional_numeric_ignored": {"Transport(2)?": "2", "Waagh": True},
        "optional_suffix_mixed": {"Scout?!": True, "Furia!": True, "Waagh": False},
    }
    frontend = _run_node_payload(ap_values=[], trait_cases=cases)["traitMap"]
    backend = {name: costs.flags_to_ability_list(flags) for name, flags in cases.items()}
    assert frontend == backend
