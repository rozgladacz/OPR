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


