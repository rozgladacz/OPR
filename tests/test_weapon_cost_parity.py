from __future__ import annotations

import json
import subprocess
import textwrap
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import costs
from app.services.costs import _weapon_cost
from tests.node_runtime import resolve_node_binary


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

    result = subprocess.run([resolve_node_binary(), "-e", node_script], check=True, capture_output=True, text=True)
    frontend = json.loads(result.stdout.strip())["cost"]

    assert frontend == pytest.approx(backend)


E2E_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "czysto_melee_wojownik",
        "quality": 4,
        "range": 0,
        "attacks": 3,
        "ap": 2,
        "weapon_traits": ["Impet", "Brutalny"],
        "unit_traits": ["wojownik"],
    },
    {
        "name": "czysto_ranged_strzelec",
        "quality": 4,
        "range": 30,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Namierzanie", "Artyleria"],
        "unit_traits": ["strzelec"],
    },
    {
        "name": "mieszane_assault",
        "quality": 4,
        "range": 18,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Assault", "Overcharge"],
        "unit_traits": [],
    },
    {
        "name": "mieszane_wojownik_cecha",
        "quality": 4,
        "range": 24,
        "attacks": 2,
        "ap": 1,
        "weapon_traits": ["Deadly(2)"],
        "unit_traits": ["wojownik"],
    },
    {
        "name": "mieszane_strzelec_cecha",
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
    weapon = type(
        "WeaponStub",
        (),
        {
            "effective_range": case["range"],
            "effective_attacks": case["attacks"],
            "effective_ap": case["ap"],
            "effective_tags": ", ".join(case["weapon_traits"]),
            "effective_cached_cost": None,
        },
    )()
    components = costs.weapon_cost_components(
        weapon,
        unit_quality=int(case["quality"]),
        unit_flags=list(case["unit_traits"]),
    )
    classification_slug = costs._roster_unit_classification(
        float(components["melee"]),
        float(components["ranged"]),
        fallback=previous_slug or "wojownik",
    )
    return {
        "classification": classification_slug,
        "melee": float(components["melee"]),
        "ranged": float(components["ranged"]),
        "total_cost": _selected_total_for_slug(
            float(components["melee"]),
            float(components["ranged"]),
            classification_slug,
        ),
    }


def _run_frontend_projection(
    scenarios: list[dict[str, Any]],
    *,
    previous_slug: str | None = None,
) -> dict[str, dict[str, Any]]:
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
          window: {{ setTimeout, clearTimeout }},
          document: {{ addEventListener: () => {{}} }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const scenarios = {json.dumps(scenarios)};
        const previousSlug = {json.dumps(previous_slug)};
        const out = {{}};
        for (const scenario of scenarios) {{
          const components = sandbox.weaponCostComponentsInternal(
            scenario.quality,
            scenario.range,
            scenario.attacks,
            scenario.ap,
            scenario.weapon_traits,
            scenario.unit_traits,
          );
          const classification = sandbox.createClassificationPayload(
            components.melee,
            components.ranged,
            new Set(['wojownik', 'strzelec']),
            previousSlug ? {{ slug: previousSlug }} : null,
          );
          const slug = classification ? classification.slug : null;
          const totalCost = slug === 'wojownik'
            ? Math.round((components.melee + components.ranged * 0.5) * 100) / 100
            : Math.round((components.ranged + components.melee * 0.5) * 100) / 100;
          out[scenario.name] = {{
            classification: slug,
            melee: components.melee,
            ranged: components.ranged,
            total_cost: totalCost,
          }};
        }}
        console.log(JSON.stringify(out));
        """
    )
    result = subprocess.run([resolve_node_binary(), "-e", node_script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout.strip())


def test_weapon_cost_end_to_end_frontend_matches_backend_components_classification_and_total() -> None:
    frontend = _run_frontend_projection(E2E_SCENARIOS)

    for case in E2E_SCENARIOS:
        backend = _backend_projection(case)
        current = frontend[case["name"]]
        assert current["classification"] == backend["classification"], case["name"]
        assert current["melee"] == pytest.approx(backend["melee"]), case["name"]
        assert current["ranged"] == pytest.approx(backend["ranged"]), case["name"]
        assert current["total_cost"] == pytest.approx(backend["total_cost"]), case["name"]


def test_weapon_cost_end_to_end_tie_break_fallback_matches_backend() -> None:
    tie_case = [
        {
            "name": "tie_equal_components",
            "quality": 4,
            "range": 18,
            "attacks": 2,
            "ap": 1,
            "weapon_traits": ["Assault"],
            "unit_traits": [],
        }
    ]

    frontend = _run_frontend_projection(tie_case, previous_slug="strzelec")
    backend = _backend_projection(tie_case[0], previous_slug="strzelec")

    result = frontend["tie_equal_components"]
    assert result["melee"] == pytest.approx(result["ranged"])
    assert result["classification"] == "strzelec"
    assert result["classification"] == backend["classification"]
    assert result["total_cost"] == pytest.approx(backend["total_cost"])

