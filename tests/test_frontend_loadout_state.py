from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"


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
