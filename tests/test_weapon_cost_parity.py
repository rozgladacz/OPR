from __future__ import annotations

import json
import subprocess
import textwrap
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.costs import _weapon_cost


@pytest.mark.parametrize(
    "case",
    [
        {
            "quality": 4,
            "range": 24,
            "attacks": 2,
            "ap": 1,
            "weapon_traits": ["Blast(3)", "Artyleria", "Limited"],
            "unit_traits": ["ostrozny", "waagh"],
        },
        {
            "quality": 4,
            "range": 18,
            "attacks": 3,
            "ap": 2,
            "weapon_traits": ["Deadly(3)", "Brutalny", "Podkrecenie", "Szturmowy"],
            "unit_traits": ["zemsta", "rezerwa", "strzelec"],
        },
        {
            "quality": 3,
            "range": 30,
            "attacks": 1.5,
            "ap": 0,
            "weapon_traits": ["Namierzanie", "Nieporeczny", "Burzaca", "Unik"],
            "unit_traits": ["zasadzka", "wojownik"],
        },
        {
            "quality": 5,
            "range": 0,
            "attacks": 4,
            "ap": 2,
            "weapon_traits": ["Impet", "Przebijajaca", "Seria"],
            "unit_traits": ["furia", "szpica"],
        },
    ],
)
def test_weapon_cost_internal_frontend_matches_backend(case: dict[str, object]) -> None:
    backend = _weapon_cost(
        int(case["quality"]),
        int(case["range"]),
        float(case["attacks"]),
        int(case["ap"]),
        list(case["weapon_traits"]),
        list(case["unit_traits"]),
    )

    node_script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const path = {json.dumps('app/static/js/app.js')};
        const code = fs.readFileSync(path, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{
            setTimeout: setTimeout,
            clearTimeout: clearTimeout,
          }},
          document: {{
            addEventListener: () => {{}},
          }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);
        const cost = sandbox.weaponCostInternal(
          {json.dumps(case['quality'])},
          {json.dumps(case['range'])},
          {json.dumps(case['attacks'])},
          {json.dumps(case['ap'])},
          {json.dumps(case['weapon_traits'])},
          {json.dumps(case['unit_traits'])},
          true,
        );
        console.log(JSON.stringify({{ cost }}));
        """
    )

    result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
    frontend = json.loads(result.stdout.strip())["cost"]

    assert frontend == pytest.approx(backend)
