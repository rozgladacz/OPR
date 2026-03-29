from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.services import costs


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
        ["node", "-e", script],
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


def test_create_classification_payload_tie_prefers_previous_classification_over_strzelec_fallback() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }
        const resolvePreviousSource = extractFunction('resolvePreviousClassificationSlug', '\\n\\nfunction createClassificationPayload');
        const createSource = extractFunction('createClassificationPayload', '\\n\\nfunction renderEditors');
        const CLASSIFICATION_SLUGS = new Set(['wojownik', 'strzelec']);
        const abilityIdentifier = (value) => String(value || '').trim().toLowerCase();
        eval(resolvePreviousSource);
        eval(createSource);

        const available = new Set(['wojownik', 'strzelec']);
        const tiedWarrior = 42;
        const tiedShooter = 42;

        const fromWarrior = createClassificationPayload(
          tiedWarrior,
          tiedShooter,
          available,
          { slug: 'wojownik' },
        );
        const fromShooter = createClassificationPayload(
          tiedWarrior,
          tiedShooter,
          available,
          { slug: 'strzelec' },
        );
        const withoutPrevious = createClassificationPayload(
          tiedWarrior,
          tiedShooter,
          available,
          null,
        );

        console.log(JSON.stringify({
          fromWarrior: fromWarrior ? fromWarrior.slug : null,
          fromShooter: fromShooter ? fromShooter.slug : null,
          withoutPrevious: withoutPrevious ? withoutPrevious.slug : null,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["fromWarrior"] == "wojownik"
    assert result["fromShooter"] == "strzelec"
    assert result["withoutPrevious"] == "wojownik"


def test_handle_state_change_refreshes_roster_total_immediately_without_server_update() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');
        const handleSource = extractFunction('handleStateChange', '\\n\\nfunction availableClassificationSlugs');

        const state = {
          totals: [],
          updateCostDisplaysCalls: 0,
          computeCalls: [],
          applyServerUpdateCalls: 0,
        };

        const makeBadge = () => ({ textContent: '' });
        const createItem = (id) => {
          const badge = makeBadge();
          const attrs = new Map([
            ['data-roster-unit-id', id],
            ['data-unit-cost', '0'],
            ['data-unit-count', '1'],
            ['data-loadout', '{}'],
            ['data-unit-classification', 'null'],
          ]);
          return {
            _badge: badge,
            _attrs: attrs,
            getAttribute(name) { return attrs.get(name) || ''; },
            setAttribute(name, value) { attrs.set(name, String(value)); },
            querySelector(selector) {
              if (selector === '[data-roster-unit-cost]') {
                return badge;
              }
              return null;
            },
            closest() {
              return { __id: id };
            },
          };
        };

        const primaryItem = createItem('u1');
        const partnerItem = createItem('u2');
        const rosterItems = [primaryItem, partnerItem];
        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return rosterItems;
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return rosterItems.find((item) => item.getAttribute('data-roster-unit-id') === match[1]) || null;
          },
        };

        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        const buildClassificationContextFromItem = (item) => ({
          id: item.getAttribute('data-roster-unit-id'),
          count: Number(item.getAttribute('data-unit-count') || '1'),
          loadoutState: JSON.parse(item.getAttribute('data-loadout') || '{}'),
          currentClassification: JSON.parse(item.getAttribute('data-unit-classification') || 'null'),
        });
        const getPartnerId = (unitId) => (unitId === 'u1' ? 'u2' : unitId === 'u2' ? 'u1' : '');
        const computeRosterItemCost = (context, partnerContext = null) => {
          state.computeCalls.push({
            unitId: context.id,
            count: context.count,
            edited: Boolean(context.loadoutState && context.loadoutState.edited),
            classification: context.currentClassification ? context.currentClassification.slug : null,
            partnerId: partnerContext ? partnerContext.id : null,
            partnerClassification: partnerContext && partnerContext.currentClassification
              ? partnerContext.currentClassification.slug
              : null,
          });
          const base = context.id === 'u1' ? 10 : 20;
          const ownClassificationBonus = context.currentClassification && context.currentClassification.slug === 'strzelec' ? 1000 : 0;
          const partnerClassificationBonus = partnerContext && partnerContext.currentClassification && partnerContext.currentClassification.slug === 'strzelec' ? 10000 : 0;
          const editedBonus = context.loadoutState && context.loadoutState.edited ? 100 : 0;
          return { total: base + context.count + editedBonus + ownClassificationBonus + partnerClassificationBonus };
        };
        const formatPoints = (value) => String(value);
        const updateTotalSummary = (value) => state.totals.push(value);

        eval(refreshSource);

        let loadoutState = { mode: 'total', passive: new Map() };
        const currentWeapons = [];
        const currentPassives = [];
        const currentBaseFlags = {};
        const abilityCostMap = new Map();
        const baseCostPerModel = 0;
        let currentCount = 5;
        const currentQuality = '';
        let currentClassification = null;
        let activeItem = primaryItem;
        const loadoutInput = { value: '{"before":1}' };
        const renderEditors = () => {};
        const serializeLoadoutState = () => '{"edited":true}';
        const updateCostDisplays = () => {
          state.updateCostDisplaysCalls += 1;
          primaryItem.setAttribute('data-unit-cost', '120');
          primaryItem.querySelector('[data-roster-unit-cost]').textContent = '120 pkt';
          return 120;
        };
        const getEntryElementFromItem = (item) => ({ __id: item.getAttribute('data-roster-unit-id') });
        const getUnitIdFromEntry = (entry) => entry.__id;
        const estimateCombinedClassification = () => ({ classification: { slug: 'strzelec' }, weaponMap: new Map() });
        const applyClassificationToState = () => {};
        const invalidateCachedAttribute = () => {};
        const updateItemClassification = (item, classification) => {
          item.setAttribute('data-unit-classification', JSON.stringify(classification ?? null));
        };
        let ignoreNextSave = false;
        let autoSaveEnabled = false;
        const setSaveStatus = () => {};
        const scheduleSave = () => {};

        eval(handleSource);

        // Symulacja lokalnej zmiany stanu oddziału (bez applyServerUpdate).
        currentCount = 6;
        loadoutInput.value = '{"edited":true}';
        handleStateChange();

        console.log(JSON.stringify({
          updateCostDisplaysCalls: state.updateCostDisplaysCalls,
          latestTotal: state.totals[state.totals.length - 1],
          unitBadge: primaryItem.querySelector('[data-roster-unit-cost]').textContent,
          unitCostAttr: primaryItem.getAttribute('data-unit-cost'),
          computeCalls: state.computeCalls,
          applyServerUpdateCalls: state.applyServerUpdateCalls,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["updateCostDisplaysCalls"] == 1
    assert result["latestTotal"] == 22137
    assert result["unitBadge"] == "11116 pkt"
    assert result["unitCostAttr"] == "11116"
    assert {
        "unitId": "u1",
        "count": 6,
        "edited": True,
        "classification": "strzelec",
        "partnerId": "u2",
        "partnerClassification": "strzelec",
    } in result["computeCalls"]
    assert {
        "unitId": "u2",
        "count": 1,
        "edited": False,
        "classification": "strzelec",
        "partnerId": "u1",
        "partnerClassification": "strzelec",
    } in result["computeCalls"]
    assert result["applyServerUpdateCalls"] == 0


def test_update_cost_displays_keeps_panel_and_unit_cost_in_sync_after_passive_toggle() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const activeCostSource = extractFunction('computeActiveItemCost', '\\n\\n  function updateCostDisplays');
        const updateCostSource = extractFunction('updateCostDisplays', '\\n\\n  function computeRosterItemCost');
        const computeSource = extractFunction('computeRosterItemCost', '\\n\\n  function refreshRosterCostBadges');

        const itemAttrs = new Map([
          ['data-roster-unit-id', 'u1'],
          ['data-unit-cost', '0'],
          ['data-unit-count', '1'],
          ['data-loadout', '{}'],
          ['data-unit-classification', JSON.stringify({ slug: 'wojownik' })],
        ]);
        const badge = { textContent: '' };
        const activeItem = {
          getAttribute(name) { return itemAttrs.get(name) || ''; },
          setAttribute(name, value) { itemAttrs.set(name, String(value)); },
          querySelector(selector) {
            if (selector === '[data-roster-unit-cost]') {
              return badge;
            }
            return null;
          },
        };
        const partnerItem = {
          getAttribute(name) {
            if (name === 'data-roster-unit-id') return 'u2';
            if (name === 'data-unit-count') return '1';
            if (name === 'data-loadout') return '{}';
            if (name === 'data-unit-classification') return JSON.stringify({ slug: 'strzelec' });
            return '';
          },
        };
        const listElement = {
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return match[1] === 'u2' ? partnerItem : null;
          },
        };

        let currentClassification = { slug: 'wojownik' };
        const loadoutState = { passive: new Map([['wojownik', 1]]) };
        const currentWeapons = [];
        const currentPassives = [];
        const currentBaseFlags = {};
        const abilityCostMap = new Map();
        const baseCostPerModel = 0;
        const currentCount = 1;
        const currentQuality = '';
        const currentWeaponCostMap = new Map();
        const getEntryElementFromItem = () => ({ __id: 'u1' });
        const getUnitIdFromEntry = (entry) => entry.__id;
        const getPartnerId = () => 'u2';
        const rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        const buildClassificationContextFromItem = (item) => ({
          id: item.getAttribute('data-roster-unit-id'),
          count: Number(item.getAttribute('data-unit-count') || '1'),
          loadoutState: { passive: new Map() },
          currentClassification: JSON.parse(item.getAttribute('data-unit-classification') || 'null'),
        });
        const estimateCombinedClassification = (context, partnerContext) => {
          if (partnerContext && partnerContext.currentClassification) {
            return { classification: partnerContext.currentClassification, weaponMap: new Map() };
          }
          return { classification: context.currentClassification, weaponMap: new Map() };
        };
        const cloneLoadoutState = (state) => ({
          passive: new Map(state.passive || []),
          active: new Map(),
          aura: new Map(),
          passiveLabels: new Map(),
          activeLabels: new Map(),
          auraLabels: new Map(),
        });
        const applyClassificationToState = (state, classification) => {
          state.passive = new Map([[classification.slug, 1]]);
        };
        const buildWeaponCostMap = () => new Map();
        const computeTotalCost = (_baseCost, _count, _weapons, _state, _abilityCosts, _passiveItems, _weaponMap) => {
          return _state.passive.has('strzelec') ? 88 : 11;
        };
        const formatPoints = (value) => String(value);
        const costValueEl = { textContent: '' };
        const costBadgeEl = { classList: { toggle: () => {} } };

        eval(computeSource);
        eval(activeCostSource);
        eval(updateCostSource);

        // Symulacja przełączenia pasywki na klasyfikację "strzelec".
        currentClassification = { slug: 'strzelec' };
        const total = updateCostDisplays();

        console.log(JSON.stringify({
          total,
          panelCost: costValueEl.textContent,
          badgeCost: badge.textContent,
          dataUnitCost: activeItem.getAttribute('data-unit-cost'),
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["total"] == 88
    assert result["panelCost"] == "88"
    assert result["badgeCost"] == "88 pkt"
    assert result["dataUnitCost"] == "88"


def test_single_unit_command_ability_keeps_unit_cost_and_roster_total_in_sync_after_full_refresh_cycle() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const prepareContextSource = extractFunction('prepareCostContext', '\\n\\n  function hydrateLoadoutStateForItem');
        const updateCostSource = extractFunction('updateCostDisplays', '\\n\\n  function computeRosterItemTotal');
        const computeTotalSource = extractFunction('computeRosterItemTotal', '\\n\\n  function computeRosterItemCost');
        const computeSource = extractFunction('computeRosterItemCost', '\\n\\n  function refreshRosterCostBadges');
        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');

        const attrs = new Map([
          ['data-roster-unit-id', 'u1'],
          ['data-unit-cost', '0'],
          ['data-unit-count', '1'],
          ['data-loadout', '{}'],
          ['data-unit-classification', 'null'],
        ]);
        const badge = { textContent: '' };
        const item = {
          getAttribute(name) { return attrs.get(name) || ''; },
          setAttribute(name, value) { attrs.set(name, String(value)); },
          querySelector(selector) {
            if (selector === '[data-roster-unit-cost]') {
              return badge;
            }
            return null;
          },
        };

        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return [item];
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return match[1] === 'u1' ? item : null;
          },
        };

        const cloneLoadoutState = (state) => ({ ...state, mode: state.mode || 'total' });
        const normalizeLoadoutStateTotals = (state) => { state.mode = 'total'; };
        const estimateCombinedClassification = (context) => ({ classification: context.currentClassification, weaponMap: new Map() });
        const applyClassificationToState = () => {};
        const buildWeaponCostMap = () => new Map();
        const computeTotalCost = (_baseCost, _count, _weapons, _state, abilityCosts) => (
          abilityCosts && abilityCosts.active instanceof Map && abilityCosts.active.get('rozkaz') ? 35 : 20
        );
        const formatPoints = (value) => String(value);
        const getPartnerId = () => '';
        const buildClassificationContextFromItem = () => ({
          loadoutState: { mode: 'total' },
          abilityCosts: { active: new Map([['rozkaz', 15]]) },
          currentClassification: null,
          count: 1,
          weapons: [],
          passiveItems: [],
          baseFlags: {},
          baseCostPerModel: 20,
          quality: 4,
        });
        const updateTotalSummaryCalls = [];
        const updateTotalSummary = (value) => updateTotalSummaryCalls.push(value);
        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        let preserveServerTotalUntilRefreshCycle = 0;
        let rosterRefreshCycleCounter = 0;

        const costValueEl = { textContent: '' };
        const costBadgeEl = { classList: { toggle: () => {} } };
        let activeItem = item;
        const loadoutState = { mode: 'total' };
        const currentWeapons = [];
        const currentPassives = [];
        const currentBaseFlags = {};
        const abilityCostMap = { active: new Map([['rozkaz', 15]]), passive: new Map() };
        const baseCostPerModel = 20;
        const currentCount = 1;
        const currentQuality = 4;
        const currentWeaponCostMap = new Map();
        const currentClassification = null;

        eval(prepareContextSource);
        eval(computeTotalSource);
        eval(computeSource);
        eval(updateCostSource);
        eval(refreshSource);

        // Lokalny cykl: dodanie aktywnej zdolności rozkazowej.
        updateCostDisplays();
        refreshRosterCostBadges({ totalOverride: null, recomputeItems: true }, 'cycle-command');

        console.log(JSON.stringify({
          dataUnitCost: item.getAttribute('data-unit-cost'),
          unitBadge: badge.textContent,
          rosterTotal: updateTotalSummaryCalls[updateTotalSummaryCalls.length - 1],
          panelCost: costValueEl.textContent,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["dataUnitCost"] == "35"
    assert result["unitBadge"] == "35 pkt"
    assert result["rosterTotal"] == 35
    assert result["panelCost"] == "35"


def test_single_item_roster_keeps_unit_cost_equal_to_roster_total_after_each_ui_change() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const prepareContextSource = extractFunction('prepareCostContext', '\\n\\n  function hydrateLoadoutStateForItem');
        const updateCostSource = extractFunction('updateCostDisplays', '\\n\\n  function computeRosterItemTotal');
        const computeTotalSource = extractFunction('computeRosterItemTotal', '\\n\\n  function computeRosterItemCost');
        const computeSource = extractFunction('computeRosterItemCost', '\\n\\n  function refreshRosterCostBadges');
        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');

        const attrs = new Map([
          ['data-roster-unit-id', 'u1'],
          ['data-unit-cost', '0'],
          ['data-unit-count', '1'],
          ['data-loadout', '{}'],
          ['data-unit-classification', 'null'],
        ]);
        const badge = { textContent: '' };
        const item = {
          getAttribute(name) { return attrs.get(name) || ''; },
          setAttribute(name, value) { attrs.set(name, String(value)); },
          querySelector(selector) {
            if (selector === '[data-roster-unit-cost]') {
              return badge;
            }
            return null;
          },
        };

        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return [item];
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return match[1] === 'u1' ? item : null;
          },
        };

        const cloneLoadoutState = (state) => ({ ...state, mode: state.mode || 'total' });
        const normalizeLoadoutStateTotals = (state) => { state.mode = 'total'; };
        const estimateCombinedClassification = (context) => ({ classification: context.currentClassification, weaponMap: new Map() });
        const applyClassificationToState = () => {};
        const buildWeaponCostMap = () => new Map();
        let dynamicCost = 20;
        const computeTotalCost = () => dynamicCost;
        const formatPoints = (value) => String(value);
        const getPartnerId = () => '';
        const buildClassificationContextFromItem = () => ({
          loadoutState: { mode: 'total' },
          abilityCosts: { active: new Map(), passive: new Map() },
          currentClassification: null,
          count: 1,
          weapons: [],
          passiveItems: [],
          baseFlags: {},
          baseCostPerModel: 0,
          quality: 4,
        });
        const totalCalls = [];
        const updateTotalSummary = (value) => totalCalls.push(value);
        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        let preserveServerTotalUntilRefreshCycle = 0;
        let rosterRefreshCycleCounter = 0;

        const costValueEl = { textContent: '' };
        const costBadgeEl = { classList: { toggle: () => {} } };
        let activeItem = item;
        const loadoutState = { mode: 'total' };
        const currentWeapons = [];
        const currentPassives = [];
        const currentBaseFlags = {};
        const abilityCostMap = { active: new Map(), passive: new Map() };
        const baseCostPerModel = 0;
        const currentCount = 1;
        const currentQuality = 4;
        const currentWeaponCostMap = new Map();
        const currentClassification = null;

        eval(prepareContextSource);
        eval(computeTotalSource);
        eval(computeSource);
        eval(updateCostSource);
        eval(refreshSource);

        const checkpoints = [];
        const step = (label, nextCost) => {
          dynamicCost = nextCost;
          updateCostDisplays();
          refreshRosterCostBadges({ totalOverride: null, recomputeItems: true }, `cycle-${label}`);
          checkpoints.push({
            label,
            unitCost: Number(item.getAttribute('data-unit-cost')),
            rosterTotal: totalCalls[totalCalls.length - 1],
            panelCost: Number(costValueEl.textContent || '0'),
          });
        };

        step('initial', 20);
        step('active-added', 35);
        step('active-removed', 20);

        console.log(JSON.stringify({ checkpoints }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["checkpoints"] == [
        {"label": "initial", "unitCost": 20, "rosterTotal": 20, "panelCost": 20},
        {"label": "active-added", "unitCost": 35, "rosterTotal": 35, "panelCost": 35},
        {"label": "active-removed", "unitCost": 20, "rosterTotal": 20, "panelCost": 20},
    ]


def test_apply_server_update_prefers_backend_cached_cost_without_immediate_frontend_recompute() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const applyServerUpdateSource = extractFunction('applyServerUpdate', '\\n\\n  function updateCostDisplays');
        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');

        const state = {
          recomputeCalls: 0,
          totals: [],
        };

        const makeItem = (id, initialCost) => {
          const attrs = new Map([
            ['data-roster-unit-id', id],
            ['data-unit-name', 'Unit'],
            ['data-unit-cost', String(initialCost)],
            ['data-selected-passives', '[]'],
            ['data-selected-actives', '[]'],
            ['data-selected-auras', '[]'],
          ]);
          const badge = { textContent: `${initialCost} pkt` };
          const loadout = { textContent: '' };
          return {
            _attrs: attrs,
            getAttribute(name) { return attrs.get(name) || ''; },
            setAttribute(name, value) { attrs.set(name, String(value)); },
            querySelector(selector) {
              if (selector === '[data-roster-unit-cost]') {
                return badge;
              }
              if (selector === '[data-roster-unit-loadout]') {
                return loadout;
              }
              if (selector === '[data-roster-unit-title]') {
                return null;
              }
              return null;
            },
            badge,
          };
        };

        const item = makeItem('u1', 120);
        const rosterItems = [item];
        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return rosterItems;
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return rosterItems.find((entry) => entry.getAttribute('data-roster-unit-id') === match[1]) || null;
          },
        };

        let activeItem = null;
        const root = listElement;
        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        const resolveUnitCacheId = (targetItem) => targetItem.getAttribute('data-roster-unit-id');
        const rosterUnitDatasetRepo = new Map();
        const rosterUnitDatasetCache = new Map();
        const UNIT_DATASET_ATTRIBUTE_MAP = new Map([['data-unit-default-summary', 'default_summary']]);
        const UNIT_DATASET_KEYS = ['default_summary'];
        const getParsedList = () => [];
        const updateUnitDataset = () => {};
        const updateListCustomName = () => {};
        const invalidateCachedAttribute = () => {};
        const setItemListAttribute = () => {};
        const formatPoints = (value) => String(value);
        const getUnitDatasetValue = () => '-';
        const updateItemClassification = () => {};
        const updateItemAbilityBadges = () => {};
        const syncEditorFromItem = () => {};
        const writeLockPairDataset = () => {};
        const applyLockPairsFromServer = () => {};
        const updateTotalSummary = (value) => state.totals.push(value);
        const buildClassificationContextFromItem = () => ({});
        const getPartnerId = () => '';
        const computeRosterItemCost = () => {
          state.recomputeCalls += 1;
          return { total: 9999 };
        };

        eval(refreshSource);
        eval(applyServerUpdateSource);

        applyServerUpdate({
          units: [{ id: 'u1', cached_cost: 450 }],
          total_cost: 450,
        });

        console.log(JSON.stringify({
          recomputeCalls: state.recomputeCalls,
          unitCostAttr: item.getAttribute('data-unit-cost'),
          unitBadge: item.badge.textContent,
          latestTotal: state.totals[state.totals.length - 1],
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["recomputeCalls"] == 0
    assert result["unitCostAttr"] == "450"
    assert result["unitBadge"] == "450 pkt"
    assert result["latestTotal"] == 450


def test_apply_server_update_keeps_server_total_and_badges_stable_without_local_edit() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const applyServerUpdateSource = extractFunction('applyServerUpdate', '\\n\\n  function updateCostDisplays');
        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');

        const state = {
          recomputeCalls: 0,
          totals: [],
        };

        const makeItem = (id, initialCost) => {
          const attrs = new Map([
            ['data-roster-unit-id', id],
            ['data-unit-name', 'Unit'],
            ['data-unit-cost', String(initialCost)],
            ['data-selected-passives', '[]'],
            ['data-selected-actives', '[]'],
            ['data-selected-auras', '[]'],
          ]);
          const badge = { textContent: `${initialCost} pkt` };
          const loadout = { textContent: '' };
          return {
            _attrs: attrs,
            getAttribute(name) { return attrs.get(name) || ''; },
            setAttribute(name, value) { attrs.set(name, String(value)); },
            querySelector(selector) {
              if (selector === '[data-roster-unit-cost]') {
                return badge;
              }
              if (selector === '[data-roster-unit-loadout]') {
                return loadout;
              }
              if (selector === '[data-roster-unit-title]') {
                return null;
              }
              return null;
            },
            badge,
          };
        };

        const firstItem = makeItem('u1', 111);
        const secondItem = makeItem('u2', 222);
        const rosterItems = [firstItem, secondItem];
        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return rosterItems;
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return rosterItems.find((entry) => entry.getAttribute('data-roster-unit-id') === match[1]) || null;
          },
        };

        let activeItem = null;
        const root = listElement;
        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        const resolveUnitCacheId = (targetItem) => targetItem.getAttribute('data-roster-unit-id');
        const rosterUnitDatasetRepo = new Map();
        const rosterUnitDatasetCache = new Map();
        const UNIT_DATASET_ATTRIBUTE_MAP = new Map([['data-unit-default-summary', 'default_summary']]);
        const UNIT_DATASET_KEYS = ['default_summary'];
        const getParsedList = () => [];
        const updateUnitDataset = () => {};
        const updateListCustomName = () => {};
        const invalidateCachedAttribute = () => {};
        const setItemListAttribute = () => {};
        const formatPoints = (value) => String(value);
        const getUnitDatasetValue = () => '-';
        const updateItemClassification = () => {};
        const updateItemAbilityBadges = () => {};
        const syncEditorFromItem = () => {};
        const writeLockPairDataset = () => {};
        const applyLockPairsFromServer = () => {};
        const updateTotalSummary = (value) => state.totals.push(value);
        const buildClassificationContextFromItem = () => ({});
        const getPartnerId = () => '';
        const computeRosterItemCost = () => {
          state.recomputeCalls += 1;
          return { total: 9999 };
        };

        eval(refreshSource);
        eval(applyServerUpdateSource);

        applyServerUpdate({
          units: [
            { id: 'u1', cached_cost: 777.7 },
            { id: 'u2', cached_cost: 765.85 },
          ],
          total_cost: 1543.55,
        });

        console.log(JSON.stringify({
          recomputeCalls: state.recomputeCalls,
          totals: state.totals,
          firstBadge: firstItem.badge.textContent,
          secondBadge: secondItem.badge.textContent,
          firstCost: firstItem.getAttribute('data-unit-cost'),
          secondCost: secondItem.getAttribute('data-unit-cost'),
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["recomputeCalls"] == 0
    assert result["totals"] == [1543.55, 1543.55]
    assert result["firstBadge"] == "777.7 pkt"
    assert result["secondBadge"] == "765.85 pkt"
    assert result["firstCost"] == "777.7"
    assert result["secondCost"] == "765.85"


def test_refresh_roster_cost_badges_applies_latest_pending_call_when_refresh_is_reentered() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');

        const state = {
          totals: [],
          phases: [],
        };

        const makeItem = (id, initialCount) => {
          const attrs = new Map([
            ['data-roster-unit-id', id],
            ['data-unit-cost', '0'],
            ['data-unit-count', String(initialCount)],
            ['data-loadout', '{}'],
            ['data-unit-classification', 'null'],
          ]);
          const badge = { textContent: '' };
          return {
            getAttribute(name) { return attrs.get(name) || ''; },
            setAttribute(name, value) { attrs.set(name, String(value)); },
            querySelector(selector) {
              if (selector === '[data-roster-unit-cost]') {
                return badge;
              }
              return null;
            },
            badge,
          };
        };

        const item = makeItem('u1', 1);
        const rosterItems = [item];
        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') {
              return rosterItems;
            }
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) {
              return null;
            }
            return rosterItems.find((entry) => entry.getAttribute('data-roster-unit-id') === match[1]) || null;
          },
        };

        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        const getPartnerId = () => '';
        const formatPoints = (value) => String(value);
        const updateTotalSummary = (value) => state.totals.push(value);
        const buildClassificationContextFromItem = (targetItem) => ({
          id: targetItem.getAttribute('data-roster-unit-id'),
          count: Number(targetItem.getAttribute('data-unit-count') || '0'),
        });

        let cycleTriggered = false;
        const computeRosterItemCost = (context) => {
          state.phases.push(`compute-${context.count}`);
          if (!cycleTriggered) {
            cycleTriggered = true;
            item.setAttribute('data-unit-count', '2');
            refreshRosterCostBadges({ totalOverride: 222, recomputeItems: true }, 'cycle-2');
          }
          return { total: context.count * 111 };
        };

        eval(refreshSource);
        refreshRosterCostBadges({ totalOverride: 111, recomputeItems: true }, 'cycle-1');

        console.log(JSON.stringify({
          totals: state.totals,
          finalBadge: item.badge.textContent,
          finalUnitCost: item.getAttribute('data-unit-cost'),
          phases: state.phases,
          lastRefreshRosterCostCycleToken,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["totals"] == [111, 222]
    assert result["finalBadge"] == "222 pkt"
    assert result["finalUnitCost"] == "222"
    assert result["phases"] == ["compute-1", "compute-2"]
    assert result["lastRefreshRosterCostCycleToken"] == "cycle-2"


def test_autosave_add_then_remove_active_restores_initial_total_after_stale_server_refresh() -> None:
    script_body = """
        const source = code;
        function extractFunction(name, endMarker) {
          const start = source.indexOf(`function ${name}(`);
          if (start === -1) {
            throw new Error(`Cannot find function ${name}`);
          }
          const end = source.indexOf(endMarker, start);
          if (end === -1) {
            throw new Error(`Cannot find end marker for ${name}`);
          }
          return source.slice(start, end);
        }

        const refreshSource = extractFunction('refreshRosterCostBadges', '\\n\\n  function applyClassificationToState');
        const handleSource = extractFunction('handleStateChange', '\\n\\nfunction availableClassificationSlugs');
        const applyServerUpdateSource = extractFunction('applyServerUpdate', '\\n\\n  function updateCostDisplays');

        const state = { totals: [], scheduledVersions: [] };
        const initialTotal = 100;

        const attrs = new Map([
          ['data-roster-unit-id', 'u1'],
          ['data-unit-name', 'Unit'],
          ['data-unit-cost', String(initialTotal)],
          ['data-unit-count', '1'],
          ['data-selected-passives', '[]'],
          ['data-selected-actives', '[]'],
          ['data-selected-auras', '[]'],
          ['data-loadout', '{}'],
          ['data-unit-classification', 'null'],
        ]);
        const badge = { textContent: `${initialTotal} pkt` };
        const item = {
          getAttribute(name) { return attrs.get(name) || ''; },
          setAttribute(name, value) { attrs.set(name, String(value)); },
          querySelector(selector) {
            if (selector === '[data-roster-unit-cost]') return badge;
            if (selector === '[data-roster-unit-loadout]') return { textContent: '' };
            if (selector === '[data-roster-unit-title]') return null;
            return null;
          },
        };

        const rosterItems = [item];
        const listElement = {
          querySelectorAll(selector) {
            if (selector === '[data-roster-item]') return rosterItems;
            return [];
          },
          querySelector(selector) {
            const match = /data-roster-unit-id="([^"]+)"/.exec(selector);
            if (!match) return null;
            return rosterItems.find((entry) => entry.getAttribute('data-roster-unit-id') === match[1]) || null;
          },
        };

        const root = listElement;
        let rosterListEl = listElement;
        const ensureRosterList = () => listElement;
        let refreshRosterCostBadgesInProgress = false;
        let pendingRefreshOptions = null;
        let pendingRefreshCycleToken = null;
        let lastRefreshRosterCostCycleToken = null;
        let refreshCycleVersion = 0;
        let latestAppliedRefreshVersion = 0;
        let latestAuthoritativeRefreshVersion = 0;
        let rosterRefreshCycleCounter = 0;
        let latestEditVersion = 0;
        const latestRequestVersion = 0;
        const nextRefreshVersion = (seedVersion = null) => {
          const seed = Number(seedVersion);
          const next = Number.isFinite(seed)
            ? Math.max(seed, latestEditVersion, refreshCycleVersion + 1)
            : Math.max(latestEditVersion, refreshCycleVersion + 1);
          refreshCycleVersion = next;
          return next;
        };
        const applyRefreshPriority = (cycleToken) => {
          const decision = resolveRosterRefreshPriority(
            { latestAppliedVersion: latestAppliedRefreshVersion, latestAuthoritativeVersion: latestAuthoritativeRefreshVersion },
            cycleToken,
          );
          latestAppliedRefreshVersion = decision.state.latestAppliedVersion;
          latestAuthoritativeRefreshVersion = decision.state.latestAuthoritativeVersion;
          return decision;
        };

        const formatPoints = (value) => String(value);
        const updateTotalSummary = (value) => state.totals.push(value);
        const resolveUnitCacheId = (targetItem) => targetItem.getAttribute('data-roster-unit-id');
        const rosterUnitDatasetRepo = new Map();
        const rosterUnitDatasetCache = new Map();
        const UNIT_DATASET_ATTRIBUTE_MAP = new Map([['data-unit-default-summary', 'default_summary']]);
        const UNIT_DATASET_KEYS = ['default_summary'];
        const getParsedList = () => [];
        const updateUnitDataset = () => {};
        const updateListCustomName = () => {};
        const invalidateCachedAttribute = () => {};
        const setItemListAttribute = () => {};
        const getUnitDatasetValue = () => '-';
        const updateItemClassification = () => {};
        const updateItemAbilityBadges = () => {};
        const syncEditorFromItem = () => {};
        const writeLockPairDataset = () => {};
        const applyLockPairsFromServer = () => {};
        const buildClassificationContextFromItem = (targetItem) => ({
          id: targetItem.getAttribute('data-roster-unit-id'),
          count: 1,
          loadoutState: JSON.parse(targetItem.getAttribute('data-loadout') || '{}'),
          currentClassification: null,
          weapons: [],
          passiveItems: [],
          baseFlags: {},
          abilityCosts: { active: new Map(), passive: new Map() },
          baseCostPerModel: 0,
          quality: 4,
        });
        const getPartnerId = () => '';
        const computeRosterItemTotal = (context) => ({ total: context.loadoutState.activeCommand ? 110 : 100 });

        let loadoutState = { mode: 'total', activeCommand: false, passive: new Map() };
        const currentWeapons = [];
        const currentPassives = [];
        const currentBaseFlags = {};
        const abilityCostMap = { active: new Map(), passive: new Map() };
        const baseCostPerModel = 0;
        let currentCount = 1;
        const currentQuality = 4;
        let currentClassification = null;
        let activeItem = item;
        const loadoutInput = { value: '{}' };
        const renderEditors = () => {};
        const serializeLoadoutState = (statePayload) => JSON.stringify(statePayload || {});
        const updateCostDisplays = () => {
          const value = loadoutState.activeCommand ? 110 : 100;
          item.setAttribute('data-unit-cost', String(value));
          item.querySelector('[data-roster-unit-cost]').textContent = `${value} pkt`;
          return value;
        };
        const getEntryElementFromItem = (targetItem) => ({ __id: targetItem.getAttribute('data-roster-unit-id') });
        const getUnitIdFromEntry = (entry) => entry.__id;
        const estimateCombinedClassification = () => ({ classification: null, weaponMap: new Map() });
        const applyClassificationToState = () => {};
        let ignoreNextSave = false;
        let autoSaveEnabled = true;
        const setSaveStatus = () => {};
        const scheduleSave = (version) => state.scheduledVersions.push(version);

        eval(refreshSource);
        eval(handleSource);
        eval(applyServerUpdateSource);

        // 1) Dodanie aktywnej zdolności + autosave.
        loadoutState.activeCommand = true;
        handleStateChange();
        const autosaveVersion = state.scheduledVersions[state.scheduledVersions.length - 1];
        applyServerUpdate(
          { units: [{ id: 'u1', cached_cost: 110 }], total_cost: 110 },
          { version: autosaveVersion, authoritative: true, dedupeKey: `server:${autosaveVersion}` },
        );

        // 2) Usunięcie aktywnej zdolności.
        loadoutState.activeCommand = false;
        handleStateChange();

        // 3) Spóźniona odpowiedź serwera z poprzedniej rewizji nie może nadpisać totala.
        applyServerUpdate(
          { units: [{ id: 'u1', cached_cost: 110 }], total_cost: 110 },
          { version: autosaveVersion, authoritative: true, dedupeKey: `server:${autosaveVersion}` },
        );

        console.log(JSON.stringify({
          totals: state.totals,
          finalTotal: state.totals[state.totals.length - 1],
          initialTotal,
          lastRefreshRosterCostCycleToken,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["finalTotal"] == result["initialTotal"]
    assert result["totals"][-1] == result["initialTotal"]


def test_build_weapon_cost_map_applies_ambush_multiplier_for_ranged_weapon() -> None:
    script_body = """
        const weapon = {
          id: 101,
          range: 24,
          attacks: 2,
          ap: 1,
          traits: '',
        };

        const withoutAmbush = sandbox.buildWeaponCostMap(
          [weapon],
          4,
          {},
          [],
          new Map(),
          null,
        ).get(weapon.id);

        const withAmbush = sandbox.buildWeaponCostMap(
          [weapon],
          4,
          { 'Zasadzka?!': true },
          [],
          new Map(),
          null,
        ).get(weapon.id);

        console.log(JSON.stringify({
          withoutAmbush,
          withAmbush,
          ratio: withAmbush / withoutAmbush,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["withoutAmbush"] > 0
    assert result["withAmbush"] < result["withoutAmbush"]
    assert result["ratio"] == 0.6


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


def test_weapon_cost_internal_applies_overcharge_multiplier_1_4() -> None:
    script_body = """
        const baseCost = sandbox.weaponCostInternal(4, 18, 2, 1, [], []);
        const overchargeCost = sandbox.weaponCostInternal(4, 18, 2, 1, ['Overcharge'], []);
        console.log(JSON.stringify({
          baseCost,
          overchargeCost,
          ratio: overchargeCost / baseCost,
        }));
    """

    script = _build_sandbox_script(script_body)
    result = _run_node(script)

    assert result["baseCost"] > 0
    assert result["overchargeCost"] > result["baseCost"]
    assert result["ratio"] == 1.4


@pytest.mark.skipif(
    not LEGACY_PARITY_ENABLED,
    reason="legacy frontend-backend math parity test (planned for removal)",
)
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


def test_render_passive_editor_formats_okopany_delta_identically_with_rezerwa_toggle() -> None:
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
            this.checked = false;
            this.disabled = false;
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
        const extractCosts = (root) => root
          .querySelectorAllByClass('roster-ability-cost')
          .map((node) => node.textContent);

        const passiveItems = [{ slug: 'Okopany', label: 'Okopany', default_count: 0, cost: 10 }];
        const passiveState = new Map([['Okopany', 1]]);
        const onChange = () => {};

        let reserveEnabled = false;
        const getDelta = () => (reserveEnabled ? 10.0001 : 9.9999);

        const withoutReserveContainer = new Element('div');
        reserveEnabled = false;
        sandbox.renderPassiveEditor(
          withoutReserveContainer,
          passiveItems,
          passiveState,
          10,
          true,
          onChange,
          getDelta,
        );
        const withoutReserveCosts = extractCosts(withoutReserveContainer);

        const withReserveContainer = new Element('div');
        reserveEnabled = true;
        sandbox.renderPassiveEditor(
          withReserveContainer,
          passiveItems,
          passiveState,
          10,
          true,
          onChange,
          getDelta,
        );
        const withReserveCosts = extractCosts(withReserveContainer);

        console.log(JSON.stringify({ withoutReserveCosts, withReserveCosts }));
    """

    result = _run_node(_build_sandbox_script(script_body))

    assert result["withoutReserveCosts"] == ["Δ +10 pkt"]
    assert result["withReserveCosts"] == ["Δ +10 pkt"]
