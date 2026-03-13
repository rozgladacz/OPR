from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from app.services import costs


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
    assert result["totalIndicators"] == ["Tryb: suma", "Tryb: suma"]
    assert result["perModelWeaponCosts"] == ["+5 pkt/model"]
    assert result["perModelAbilityCosts"] == ["+3 pkt/model"]
    assert result["perModelIndicators"] == ["Tryb: pkt/model", "Tryb: pkt/model"]
