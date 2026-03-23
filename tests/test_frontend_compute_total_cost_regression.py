from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from app import models
from app.services import costs


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
            aura: new Map(Object.entries(testCase.aura || {{}}).map(([k, v]) => [String(k), Number(v)])),
            baseActive: new Map(Object.entries(testCase.baseActive || {{}}).map(([k, v]) => [String(k), Number(v)])),
            baseAura: new Map(Object.entries(testCase.baseAura || {{}}).map(([k, v]) => [String(k), Number(v)])),
            passive: new Map(Object.entries(testCase.passive || {{}}).map(([k, v]) => [String(k), Number(v)])),
            activeLabels: new Map(Object.entries(testCase.activeLabels || {{}}).map(([k, v]) => [String(k), String(v)])),
            auraLabels: new Map(Object.entries(testCase.auraLabels || {{}}).map(([k, v]) => [String(k), String(v)])),
            baseActiveLabels: new Map(Object.entries(testCase.baseActiveLabels || {{}}).map(([k, v]) => [String(k), String(v)])),
            baseAuraLabels: new Map(Object.entries(testCase.baseAuraLabels || {{}}).map(([k, v]) => [String(k), String(v)])),
          }};
          const total = sandbox.computeTotalCost(
            testCase.basePerModel,
            testCase.modelCount,
            testCase.weaponOptions,
            state,
            {{
              active: new Map(Object.entries(testCase.activeCosts || {{}})),
              passive: new Map(Object.entries(testCase.passiveCosts || {{}})),
              activeIdentifiers: new Map(Object.entries(testCase.activeIdentifiers || {{}})),
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


def test_compute_total_cost_matches_backend_for_massive_with_ociezalosc() -> None:
    ability = models.Ability(id=101, name="Ociężałość", type="aura", description="")
    link = models.UnitAbility(position=0)
    link.ability = ability

    unit = models.Unit(
        name="Massive Unit",
        quality=4,
        defense=4,
        toughness=3,
        flags="Masywny",
        army_id=1,
    )
    unit.abilities = [link]
    unit.weapon_links = []
    unit.default_weapon = None
    unit.default_weapon_id = None

    roster_unit = models.RosterUnit(unit=unit, count=3)
    backend_without = costs.roster_unit_role_totals(
        roster_unit,
        {"mode": "per_model", "aura": {str(ability.id): 0}},
    )
    backend_with = costs.roster_unit_role_totals(
        roster_unit,
        {"mode": "per_model", "aura": {str(ability.id): 1}},
    )
    backend_diff = backend_with["wojownik"] - backend_without["wojownik"]

    cases = [
        {
            "name": "frontend_massive_ociezalosc",
            "mode": "per_model",
            "basePerModel": 0,
            "modelCount": 3,
            "weaponOptions": [],
            "aura": {str(ability.id): 1},
            "activeCosts": {str(ability.id): costs.ability_cost_from_name("Ociężałość")},
            "passiveItems": [
                {"slug": "masywny", "default_count": 1, "cost": 0},
            ],
        },
    ]
    totals = _run_compute_total_cost_cases(cases)

    assert totals["frontend_massive_ociezalosc"] == backend_diff


def test_compute_total_cost_prefers_active_slug_identifiers_for_passive_interactions() -> None:
    cases = [
        {
            "name": "odwody_without_blocking_active",
            "mode": "total",
            "basePerModel": 0,
            "modelCount": 1,
            "weaponOptions": [],
            "active": {"101": 0},
            "passive": {"odwody": 1},
            "passiveItems": [{"slug": "odwody", "default_count": 0, "cost": -2.5}],
            "passiveCosts": {"odwody": -2.5},
        },
        {
            "name": "odwody_with_blocking_active_slug",
            "mode": "total",
            "basePerModel": 0,
            "modelCount": 1,
            "weaponOptions": [],
            "active": {"101": 1},
            "activeIdentifiers": {"101": "zasadzka"},
            "passive": {"odwody": 1},
            "passiveItems": [{"slug": "odwody", "default_count": 0, "cost": -2.5}],
            "passiveCosts": {"odwody": -2.5},
        },
    ]
    totals = _run_compute_total_cost_cases(cases)

    assert totals["odwody_without_blocking_active"] == -2.5
    assert totals["odwody_with_blocking_active_slug"] == 0
