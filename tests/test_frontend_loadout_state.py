from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.services import costs
from tests.node_runtime import resolve_node_binary


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"
LEGACY_PARITY_ENABLED = os.getenv("ENABLE_LEGACY_MATH_PARITY_TESTS", "").strip() in {
    "1",
    "true",
    "yes",
}


def _build_sandbox_script(body: str) -> str:
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const path = {json.dumps(str(APP_JS_PATH))};
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
        {body}
        """
    )


def _run_node(script: str) -> dict[str, object]:
    result = subprocess.run(
        [resolve_node_binary(), "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    assert stdout, "Node script produced no output"
    return json.loads(stdout)


def test_loadout_state_preserves_aura_variant_counts() -> None:
    banner_key = "aura::banner"
    medic_key = "aura::medic"
    aura_items = [
        {
            "ability_id": 50,
            "loadout_key": banner_key,
            "default_count": 2,
            "label": "Sztandar",
        },
        {
            "ability_id": 50,
            "loadout_key": medic_key,
            "default_count": 1,
            "label": "Medyk",
        },
    ]

    script_body = f"""
        const bannerKey = {json.dumps(banner_key)};
        const medicKey = {json.dumps(medic_key)};
        const auraItems = {json.dumps(aura_items)};
        const state = sandbox.createLoadoutState({{}});
        sandbox.ensureStateEntries(state.aura, auraItems, 'ability_id', 'default_count', {{ fallbackIdKeys: ['id'] }});
        state.aura.set(bannerKey, 3);
        state.aura.set(medicKey, 1);
        state.auraLabels.set(bannerKey, 'Sztandar');
        state.auraLabels.set(medicKey, 'Medyk');
        const serialized = JSON.parse(sandbox.serializeLoadoutState(state));
        const reloaded = sandbox.createLoadoutState(serialized);
        console.log(JSON.stringify({{
          initialKeys: Array.from(state.aura.keys()),
          serializedAura: serialized.aura.sort((a, b) => a.id.localeCompare(b.id)),
          serializedLabels: serialized.aura_labels.sort((a, b) => a.id.localeCompare(b.id)),
          reloadedCounts: [reloaded.aura.get(bannerKey), reloaded.aura.get(medicKey)],
        }}));
    """

    script = _build_sandbox_script(script_body)

    result = _run_node(script)

    assert result["initialKeys"] == [banner_key, medic_key]

    serialized_aura = result["serializedAura"]
    assert serialized_aura == [
        {"id": banner_key, "count": 3},
        {"id": medic_key, "count": 1},
    ]

    serialized_labels = result["serializedLabels"]
    assert serialized_labels == [
        {"id": banner_key, "name": "Sztandar"},
        {"id": medic_key, "name": "Medyk"},
    ]

    assert result["reloadedCounts"] == [3, 1]


def test_compute_total_cost_uses_open_transport_multiplier_with_active_traits() -> None:
    script_body = """
        const passiveItems = [
          {
            slug: 'otwarty_transport(2)',
            value: '2',
            label: 'Otwarty Transport(2)',
            raw: 'Otwarty Transport(2)',
            default_count: 0,
            is_army_rule: false,
            cost: 999,
          },
          {
            slug: 'transport(2)',
            value: '2',
            label: 'Transport(2)',
            raw: 'Transport(2)',
            default_count: 0,
            is_army_rule: false,
            cost: 999,
          },
        ];
        const state = sandbox.createLoadoutState({
          active: [
            { id: 'samolot', count: 1 },
          ],
          passive: [
            { id: 'otwarty_transport(2)', count: 1 },
            { id: 'transport(2)', count: 1 },
          ],
        });
        const total = sandbox.computeTotalCost(
          0,
          1,
          [],
          state,
          { active: new Map(), passive: new Map() },
          passiveItems,
          new Map(),
        );
        console.log(JSON.stringify({ total }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    # transport(2) with 'samolot' => 2 * 3.5 = 7
    # otwarty_transport(2) with 'samolot' => 2 * (3.5 + 0.25) = 7.5
    assert result["total"] == 14.5


def test_compute_total_cost_keeps_open_transport_dynamic_when_payload_cost_is_zero() -> None:
    script_body = """
        const passiveItems = [
          {
            slug: 'otwarty_transport(2)',
            value: '2',
            label: 'Otwarty Transport(2)',
            raw: 'Otwarty Transport(2)',
            default_count: 0,
            is_army_rule: false,
            cost: 0,
          },
        ];
        const state = sandbox.createLoadoutState({
          active: [
            { id: 'samolot', count: 1 },
          ],
          passive: [
            { id: 'otwarty_transport(2)', count: 1 },
          ],
        });
        const total = sandbox.computeTotalCost(
          0,
          1,
          [],
          state,
          { active: new Map(), passive: new Map([['otwarty_transport(2)', 0]]) },
          passiveItems,
          new Map(),
        );
        console.log(JSON.stringify({ total }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    # otwarty_transport(2) with 'samolot' => 2 * (3.5 + 0.25) = 7.5
    assert result["total"] == 7.5


def test_build_weapon_cost_map_ignores_army_rule_off_flags_when_collecting_unit_traits() -> None:
    script_body = """
        const weapon = {
          id: 101,
          range: 24,
          attacks: 2,
          ap: 1,
          traits: '',
        };

        const captured = { unitTraits: [] };
        const originalWeaponCostInternal = sandbox.weaponCostInternal;
        sandbox.weaponCostInternal = function (quality, range, attacks, ap, traits, unitTraits, allowAssaultExtra) {
          captured.unitTraits = Array.isArray(unitTraits) ? [...unitTraits] : [];
          return originalWeaponCostInternal(quality, range, attacks, ap, traits, unitTraits, allowAssaultExtra);
        };

        sandbox.buildWeaponCostMap(
          [weapon],
          4,
          { '__army_off__samolot': true },
          [],
          new Map(),
          null,
        );

        console.log(JSON.stringify(captured));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert "samolot" not in result["unitTraits"]


def test_weapon_cost_internal_applies_ambush_only_to_ranged_part_of_assault_weapon() -> None:
    script_body = """
        const rangedNoAmbush = sandbox.weaponCostInternal(
          4,
          18,
          2,
          1,
          ['Szturmowa'],
          [],
          false,
        );
        const meleeNoAmbush = sandbox.weaponCostInternal(
          4,
          0,
          2,
          1,
          ['Szturmowa'],
          [],
          false,
        );
        const withAmbush = sandbox.weaponCostInternal(
          4,
          18,
          2,
          1,
          ['Szturmowa'],
          ['Zasadzka'],
          true,
        );

        console.log(JSON.stringify({
          rangedNoAmbush,
          meleeNoAmbush,
          withAmbush,
          expected: rangedNoAmbush * 0.6 + meleeNoAmbush,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["withAmbush"] == pytest.approx(result["expected"], rel=1e-6, abs=1e-6)


def test_weapon_cost_internal_applies_reserve_to_both_assault_components() -> None:
    script_body = """
        const rangedNoReserve = sandbox.weaponCostInternal(
          4,
          18,
          2,
          1,
          ['Szturmowa'],
          [],
          false,
        );
        const meleeNoReserve = sandbox.weaponCostInternal(
          4,
          0,
          2,
          1,
          ['Szturmowa'],
          [],
          false,
        );
        const withReserve = sandbox.weaponCostInternal(
          4,
          18,
          2,
          1,
          ['Szturmowa'],
          ['Rezerwa'],
          true,
        );

        console.log(JSON.stringify({
          rangedNoReserve,
          meleeNoReserve,
          withReserve,
          expected: (rangedNoReserve + meleeNoReserve) * 0.6,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["withReserve"] == pytest.approx(result["expected"], rel=1e-6, abs=1e-6)


def test_build_weapon_cost_map_applies_reserve_when_base_flag_is_optional_label() -> None:
    script_body = """
        const weapon = {
          id: 201,
          range: 18,
          attacks: 2,
          ap: 1,
          traits: 'Szturmowa',
        };

        const baseFlags = { 'Rezerwa?': true };
        const passiveItems = [{ slug: 'Rezerwa', default_count: 0, is_mandatory: false }];
        const passiveState = new Map([['Rezerwa', 1]]);

        const withoutReserve = sandbox.buildWeaponCostMap(
          [weapon],
          4,
          baseFlags,
          passiveItems,
          new Map(),
          null,
        ).get(weapon.id);

        const withReserve = sandbox.buildWeaponCostMap(
          [weapon],
          4,
          baseFlags,
          passiveItems,
          passiveState,
          null,
        ).get(weapon.id);

        console.log(JSON.stringify({
          withoutReserve,
          withReserve,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["withoutReserve"] > 0
    assert result["withReserve"] < result["withoutReserve"]


def test_compute_total_cost_with_rezerwa_uses_base_passive_component_and_weapon_preview_delta() -> None:
    script_body = """
        const weapon = {
          id: 201,
          range: 12,
          attacks: 1,
          ap: 1,
          traits: '',
          cost: sandbox.weaponCostInternal(4, 12, 1, 1, [], [], true),
        };

        const withoutReserveWeapon = sandbox.weaponCostInternal(4, 12, 1, 1, [], [], true);
        const withReserveWeapon = sandbox.weaponCostInternal(4, 12, 1, 1, [], ['Rezerwa'], true);
        const passiveTotalDelta = withReserveWeapon - withoutReserveWeapon;

        const passiveItems = [
          {
            slug: 'Rezerwa',
            default_count: 0,
            cost: passiveTotalDelta,
            cost_base: 0,
          },
        ];

        const baseState = sandbox.createLoadoutState({
          mode: 'per_model',
          weapons: [{ id: 201, count: 1 }],
          passive: [{ id: 'Rezerwa', count: 0 }],
        });
        const reserveState = sandbox.createLoadoutState({
          mode: 'per_model',
          weapons: [{ id: 201, count: 1 }],
          passive: [{ id: 'Rezerwa', count: 1 }],
        });

        const totalWithout = sandbox.computeTotalCost(
          0,
          10,
          [weapon],
          baseState,
          { active: new Map(), passive: new Map([['Rezerwa', 0]]) },
          passiveItems,
          new Map([[201, withoutReserveWeapon]]),
        );
        const totalWith = sandbox.computeTotalCost(
          0,
          10,
          [weapon],
          reserveState,
          { active: new Map(), passive: new Map([['Rezerwa', 0]]) },
          passiveItems,
          new Map([[201, withReserveWeapon]]),
        );

        console.log(JSON.stringify({
          totalWithout,
          totalWith,
          delta: totalWith - totalWithout,
          expected: (withReserveWeapon - withoutReserveWeapon) * 10,
          doubledExpected: (withReserveWeapon - withoutReserveWeapon) * 20,
        }));
    """
    result = _run_node(_build_sandbox_script(script_body))

    assert result["delta"] == pytest.approx(result["expected"], abs=1e-6)
    assert result["delta"] != pytest.approx(result["doubledExpected"], abs=1e-6)
    assert result["delta"] == pytest.approx(-19.67, abs=0.5)


def test_passive_cost_delta_depends_on_other_traits_frontend_matches_backend() -> None:
    passive_items = [
        {
            "slug": "transport(2)",
            "value": "2",
            "label": "Transport(2)",
            "raw": "Transport(2)",
            "default_count": 0,
            "is_army_rule": False,
            "cost": 999,
        }
    ]

    script_body = f"""
        const passiveItems = {json.dumps(passive_items)};
        const evaluate = (activeTrait) => {{
          const state = sandbox.createLoadoutState({{
            active: activeTrait ? [{{ id: activeTrait, count: 1 }}] : [],
            passive: [{{ id: 'transport(2)', count: 1 }}],
          }});
          return sandbox.computeTotalCost(
            0,
            1,
            [],
            state,
            {{ active: new Map(), passive: new Map() }},
            passiveItems,
            new Map(),
          );
        }};
        const noTrait = evaluate(null);
        const withPlane = evaluate('samolot');
        console.log(JSON.stringify({{ noTrait, withPlane, delta: withPlane - noTrait }}));
    """
    frontend = _run_node(_build_sandbox_script(script_body))

    base_multiplier = 1.0
    plane_multiplier = next(
        value for slugs, value in costs.TRANSPORT_MULTIPLIERS if "samolot" in slugs
    )
    backend_no_trait = 2 * base_multiplier
    backend_with_plane = 2 * plane_multiplier

    assert frontend["noTrait"] == backend_no_trait
    assert frontend["withPlane"] == backend_with_plane
    assert frontend["delta"] == backend_with_plane - backend_no_trait


def test_compute_total_cost_total_mode_binary_okopany_scales_for_full_unit() -> None:
    script_body = """
        const perModelCost = 2;
        const state = sandbox.createLoadoutState({
          mode: 'total',
          passive: [{ id: 'Okopany', count: 1 }],
        });
        const total = sandbox.computeTotalCost(
          0,
          10,
          [],
          state,
          { active: new Map(), passive: new Map([['Okopany', perModelCost]]) },
          [{ slug: 'Okopany', default_count: 0, cost: perModelCost }],
          new Map(),
        );
        console.log(JSON.stringify({ total, expected: perModelCost * 10 }));
    """

    result = _run_node(_build_sandbox_script(script_body))

    assert result["total"] == result["expected"] == 20


def test_render_editors_show_mode_indicator_and_cost_labels_after_mode_switch() -> None:
    script_body = """
        class Element {
          constructor(tag) {
            this.tagName = String(tag || '').toUpperCase();
            this.children = [];
            this.className = '';
            this.textContent = '';
            this.title = '';
            this.value = '';
            this.type = '';
            this.min = '';
            this.max = '';
            this.parentNode = null;
            this._listeners = new Map();
            this._innerHTML = '';
          }
          appendChild(child) {
            if (child && typeof child === 'object') {
              child.parentNode = this;
              this.children.push(child);
            }
            return child;
          }
          setAttribute(name, value) {
            this[name] = String(value);
          }
          set innerHTML(value) {
            this._innerHTML = String(value || '');
            this.children = [];
          }
          get innerHTML() {
            return this._innerHTML;
          }
          addEventListener(type, handler) {
            this._listeners.set(type, handler);
          }
          get childElementCount() {
            return this.children.length;
          }
          querySelectorAllByClass(className) {
            const wanted = String(className || '').trim();
            const out = [];
            const hasClass = (node, cls) => {
              const classes = String(node.className || '').split(/\\s+/).filter(Boolean);
              return classes.includes(cls);
            };
            const walk = (node) => {
              if (!node || !Array.isArray(node.children)) {
                return;
              }
              node.children.forEach((child) => {
                if (hasClass(child, wanted)) {
                  out.push(child);
                }
                walk(child);
              });
            };
            walk(this);
            return out;
          }
        }

        sandbox.document.createElement = (tag) => new Element(tag);

        const makeContainer = () => {
          const root = new Element('div');
          root.innerHTML = '';
          return root;
        };
        const extractTexts = (root, className) => root
          .querySelectorAllByClass(className)
          .map((node) => node.textContent);

        const weaponContainer = makeContainer();
        const abilityContainer = makeContainer();

        const weaponOptions = [{
          id: 7,
          name: 'Karabin',
          cost: 5,
          range: 24,
          attacks: 1,
          ap: 0,
          traits: '',
          default_count: 1,
          is_default: true,
          is_primary: true,
        }];
        const abilityItems = [{
          ability_id: 11,
          label: 'Szarża',
          cost: 3,
          default_count: 1,
        }];

        const noop = () => {};

        sandbox.renderWeaponEditor(weaponContainer, weaponOptions, new Map(), 3, true, noop, 'total');
        sandbox.renderAbilityEditor(abilityContainer, abilityItems, new Map(), null, 3, true, noop, 'total');
        const totalWeaponCosts = extractTexts(weaponContainer, 'roster-ability-cost');
        const totalAbilityCosts = extractTexts(abilityContainer, 'roster-ability-cost');
        const totalIndicators = extractTexts(weaponContainer, 'roster-mode-indicator')
          .concat(extractTexts(abilityContainer, 'roster-mode-indicator'));

        sandbox.renderWeaponEditor(weaponContainer, weaponOptions, new Map(), 3, true, noop, 'per_model');
        sandbox.renderAbilityEditor(abilityContainer, abilityItems, new Map(), null, 3, true, noop, 'per_model');
        const perModelWeaponCosts = extractTexts(weaponContainer, 'roster-ability-cost');
        const perModelAbilityCosts = extractTexts(abilityContainer, 'roster-ability-cost');
        const perModelIndicators = extractTexts(weaponContainer, 'roster-mode-indicator')
          .concat(extractTexts(abilityContainer, 'roster-mode-indicator'));

        console.log(JSON.stringify({
          totalWeaponCosts,
          totalAbilityCosts,
          totalIndicators,
          perModelWeaponCosts,
          perModelAbilityCosts,
          perModelIndicators,
        }));
    """

    result = _run_node(_build_sandbox_script(script_body))

    assert result["totalWeaponCosts"] == ["+5 pkt"]
    assert result["totalAbilityCosts"] == ["+3 pkt"]
    assert result["totalIndicators"] == []
    assert result["perModelWeaponCosts"] == ["+5 pkt/model"]
    assert result["perModelAbilityCosts"] == ["+3 pkt/model"]
    assert result["perModelIndicators"] == ["Tryb: pkt/model", "Tryb: pkt/model"]


def test_weapon_cost_components_internal_matches_legacy_total_without_classification() -> None:
    script_body = """
        const components = sandbox.weaponCostComponentsInternal(
          4,
          24,
          2,
          1,
          ['Assault', 'Deadly(2)'],
          [],
        );
        const legacy = sandbox.weaponCostInternal(
          4,
          24,
          2,
          1,
          ['Assault', 'Deadly(2)'],
          [],
          true,
        );
        console.log(JSON.stringify({
          components,
          legacy: Math.round(legacy * 100) / 100,
          sum: Math.round((components.melee + components.ranged) * 100) / 100,
        }));
    """

    result = _run_node(_build_sandbox_script(script_body))

    assert result["components"]["melee"] > 0
    assert result["components"]["ranged"] > 0
    assert result["components"]["total"] == pytest.approx(result["legacy"], abs=0.01)
    assert result["sum"] == pytest.approx(result["legacy"], abs=0.01)
