(function () {
  "use strict";

  const STORAGE_PREFIX = "opr.battleState.";
  const MELEE_ASSAULT_TRAITS = new Set(["szturmowy", "szturmowa", "assault"]);
  const UNWIELDY_TRAITS = new Set(["nieporeczna", "unwieldy"]);

  // Status buttons config: key → {selector, btn color} — order matches template
  const STATUS_CONFIGS = [
    { key: "activated", selector: '[data-status-toggle="activated"]', color: "primary"   },
    { key: "entrenched",selector: '[data-status-toggle="entrenched"]',color: "success"   },
    { key: "pinned",    selector: '[data-status-toggle="pinned"]',    color: "warning"   },
    { key: "fatigued",  selector: '[data-status-toggle="fatigued"]',  color: "secondary" },
    { key: "defeated",  selector: "[data-defeated-toggle]",           color: "danger"    },
  ];

  function normalizeSlug(value) {
    if (value == null) return "";
    let text = String(value).trim().toLowerCase();
    if (text.normalize) {
      text = text.normalize("NFD").replace(/[̀-ͯ]/g, "");
    }
    return text;
  }

  function isAssaultTrait(trait) {
    return MELEE_ASSAULT_TRAITS.has(normalizeSlug(trait));
  }

  function isUnwieldyTrait(trait) {
    return UNWIELDY_TRAITS.has(normalizeSlug(trait));
  }

  function parseRangeInt(weapon) {
    if (typeof weapon.range_int === "number" && Number.isFinite(weapon.range_int)) {
      return weapon.range_int;
    }
    const raw = weapon.range;
    if (raw == null || raw === "") return 0;
    const text = String(raw).trim().toLowerCase();
    if (text === "melee" || text === "m") return 0;
    const num = parseInt(text.replace(/[^0-9-]/g, ""), 10);
    return Number.isFinite(num) ? num : 0;
  }

  function isMelee(weapon) {
    return parseRangeInt(weapon) === 0;
  }

  function traitsList(weapon) {
    if (Array.isArray(weapon.traits_list)) return weapon.traits_list;
    const raw = weapon.traits;
    if (!raw) return [];
    return String(raw).split(",").map((t) => t.trim()).filter(Boolean);
  }

  function traitBaseName(trait) {
    return trait.split("(")[0].trim();
  }

  function makeTooltipSpan(text, suffix) {
    const descs = window._abilityDescriptions;
    const desc = (descs && (descs[text] || descs[traitBaseName(text)])) || "";
    const s = document.createElement("span");
    s.textContent = text + (suffix || "");
    if (desc) {
      s.dataset.bsToggle = "tooltip";
      s.dataset.bsPlacement = "top";
      s.dataset.bsTitle = desc;
    }
    return s;
  }

  function effectiveIsPrimary(weapon, idx, us) {
    const key = weaponKey(weapon, idx);
    if (us.primaryOverrides && key in us.primaryOverrides) {
      return !!us.primaryOverrides[key];
    }
    return !!weapon.is_primary;
  }

  function storageKey(rosterId) {
    return STORAGE_PREFIX + String(rosterId);
  }

  function loadState(rosterId) {
    try {
      const raw = window.localStorage.getItem(storageKey(rosterId));
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveState(rosterId, state) {
    try {
      window.localStorage.setItem(storageKey(rosterId), JSON.stringify(state));
    } catch (e) { /* noop */ }
  }

  function clearState(rosterId) {
    try {
      window.localStorage.removeItem(storageKey(rosterId));
    } catch (e) { /* noop */ }
  }

  function weaponKey(weapon, idx) {
    if (weapon.weapon_id != null) return "w" + weapon.weapon_id;
    return "i" + idx;
  }

  function unitInitialState(card) {
    const initialModels = parseInt(card.dataset.initialModels || "0", 10) || 0;
    let weapons = [];
    try { weapons = JSON.parse(card.dataset.weaponsJson || "[]") || []; } catch (e) { weapons = []; }
    const weaponCounts = {};
    weapons.forEach((w, idx) => {
      const key = weaponKey(w, idx);
      const c = parseInt(w.count, 10);
      weaponCounts[key] = Number.isFinite(c) && c >= 0 ? c : 0;
    });
    return {
      defeated: false,
      pinned: false,
      fatigued: false,
      entrenched: false,
      activated: false,
      activeModels: initialModels,
      woundsRemaining: 0,
      weapons: weaponCounts,
      primaryOverrides: {},
      mode: "equipment",
      struckAbilities: [],
    };
  }

  function getCards() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-battle-unit]"));
  }

  function buildModeToolbar(card, weapons) {
    const toolbar = card.querySelector("[data-mode-toolbar]");
    if (!toolbar) return;
    toolbar.querySelectorAll("[data-mode^='ranged:']").forEach((b) => b.remove());
    const ranges = new Set();
    weapons.forEach((w) => {
      const r = parseRangeInt(w);
      if (r > 0) ranges.add(r);
    });
    Array.from(ranges).sort((a, b) => a - b).forEach((r) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-outline-secondary";
      btn.dataset.mode = "ranged:" + r;
      btn.textContent = r + '"';
      toolbar.appendChild(btn);
    });
  }

  function filterWeaponsForMode(weapons, mode, unitState) {
    return weapons
      .map((w, idx) => ({ weapon: w, idx, key: weaponKey(w, idx) }))
      .filter((entry) => {
        const active = unitState.weapons[entry.key] || 0;
        if (active <= 0) return false;
        const w = entry.weapon;
        const range = parseRangeInt(w);
        const traits = traitsList(w);
        if (mode === "equipment") return true;
        if (mode === "melee") {
          if (range === 0) return true;
          return traits.some(isAssaultTrait);
        }
        if (mode.startsWith("ranged:")) {
          const r = parseInt(mode.slice(7), 10);
          if (!Number.isFinite(r)) return false;
          if (range < r) return false;
          if (r === 12 && traits.some(isUnwieldyTrait)) return false;
          return true;
        }
        return true;
      });
  }

  function groupAttacks(filtered) {
    const groups = new Map();
    filtered.forEach((entry) => {
      const w = entry.weapon;
      const activeCount = entry.activeCount || 0;
      const attacksPer = parseFloat(w.attacks);
      const a = Number.isFinite(attacksPer) ? attacksPer : 1;
      const traits = traitsList(w).filter((t) => !isAssaultTrait(t));
      const ap = w.ap == null ? 0 : parseInt(w.ap, 10) || 0;
      const traitKey = traits.map(normalizeSlug).sort().join("|");
      const key = ap + "|" + traitKey;
      const total = a * activeCount;
      if (groups.has(key)) {
        groups.get(key).totalAttacks += total;
      } else {
        groups.set(key, { ap, traits, totalAttacks: total });
      }
    });
    return Array.from(groups.values()).sort((a, b) => {
      if (b.totalAttacks !== a.totalAttacks) return b.totalAttacks - a.totalAttacks;
      return a.ap - b.ap;
    });
  }

  function formatAttacks(value) {
    if (Math.abs(value - Math.round(value)) < 0.01) return String(Math.round(value));
    return value.toFixed(1);
  }

  function disposeTooltipsIn(container) {
    if (typeof bootstrap === "undefined" || !bootstrap.Tooltip) return;
    container.querySelectorAll("[data-bs-toggle='tooltip']").forEach(function (el) {
      const inst = bootstrap.Tooltip.getInstance(el);
      if (inst) inst.dispose();
    });
  }

  function renderUnit(card, unitState) {
    const weapons = parseWeaponsCached(card);
    const toughness = parseInt(card.dataset.toughness || "1", 10) || 1;

    // Model counter
    const modelsValue = card.querySelector("[data-models-value]");
    if (modelsValue) modelsValue.textContent = unitState.activeModels;

    // Wounds counter
    const woundsValue = card.querySelector("[data-wounds-value]");
    const woundsMax = card.querySelector("[data-wounds-max]");
    if (woundsValue) woundsValue.textContent = unitState.woundsRemaining;
    if (woundsMax) woundsMax.textContent = unitState.activeModels * toughness;

    // Status buttons
    STATUS_CONFIGS.forEach(({ key, selector, color }) => {
      const btn = card.querySelector(selector);
      if (!btn) return;
      const isActive = key === "defeated" ? !!unitState.defeated : !!unitState[key];
      if (isActive) {
        btn.classList.remove("btn-outline-" + color);
        btn.classList.add("btn-" + color, "active");
      } else {
        btn.classList.remove("btn-" + color, "active");
        btn.classList.add("btn-outline-" + color);
      }
    });

    card.classList.toggle("is-defeated", !!unitState.defeated);

    // Mode toolbar active state
    const toolbar = card.querySelector("[data-mode-toolbar]");
    if (toolbar) {
      toolbar.querySelectorAll("[data-mode]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.mode === unitState.mode);
      });
    }

    const list = card.querySelector("[data-weapon-list]");
    const summary = card.querySelector("[data-attack-summary]");
    if (!list || !summary) return;

    disposeTooltipsIn(list);
    disposeTooltipsIn(summary);
    list.innerHTML = "";
    summary.innerHTML = "";

    const initialWeapons = weapons.map((w, idx) => ({
      weapon: w,
      idx,
      key: weaponKey(w, idx),
      initialCount: parseInt(w.count, 10) || 0,
      activeCount: unitState.weapons[weaponKey(w, idx)] || 0,
    }));

    if (unitState.mode === "equipment") {
      summary.classList.add("d-none");
      initialWeapons.forEach((entry) => {
        const w = entry.weapon;
        const line = document.createElement("div");
        line.className = "weapon-line";
        line.dataset.battleWeapon = entry.key;
        line.dataset.active = entry.activeCount > 0 ? "1" : "0";

        const labelWrap = document.createElement("div");
        labelWrap.className = "weapon-label-wrap d-flex align-items-center gap-1";

        const dec = document.createElement("button");
        dec.type = "button";
        dec.className = "btn btn-outline-secondary btn-sm counter-btn";
        dec.textContent = "−";
        dec.dataset.weaponDecrement = entry.key;

        const valueSpan = document.createElement("span");
        valueSpan.className = "counter-value";
        valueSpan.textContent = entry.activeCount;

        const initialSpan = document.createElement("span");
        initialSpan.className = "text-muted small";
        initialSpan.textContent = "/ " + entry.initialCount;

        const inc = document.createElement("button");
        inc.type = "button";
        inc.className = "btn btn-outline-secondary btn-sm counter-btn";
        inc.textContent = "+";
        inc.dataset.weaponIncrement = entry.key;

        const labelText = document.createElement("span");
        labelText.className = "weapon-label ms-2";
        labelText.style.cursor = "pointer";
        const isPrimary = effectiveIsPrimary(w, entry.idx, unitState);
        labelText.textContent = (isPrimary ? "⚑ " : "") + (w.name || "Broń");
        labelText.dataset.weaponPrimaryToggle = entry.key;
        const rangeDisp = parseRangeInt(w) || "wręcz";
        const trDisp = w.traits || "-";
        labelText.dataset.bsToggle = "tooltip";
        labelText.dataset.bsPlacement = "top";
        labelText.dataset.bsTitle = "Ataki: " + (w.attacks ?? "-") + " | Zasięg: " + rangeDisp + " | AP: " + (w.ap ?? "-") + " | Cechy: " + trDisp;

        [dec, valueSpan, initialSpan, inc, labelText].forEach((el) => labelWrap.appendChild(el));

        const stats = document.createElement("span");
        stats.className = "weapon-stats";
        const range = parseRangeInt(w);
        const attacks = w.attacks == null ? "-" : w.attacks;
        const ap = w.ap == null ? "-" : w.ap;
        stats.appendChild(document.createTextNode(
          "Ataki: " + attacks + " | Zasięg: " + (range || "wręcz") + " | AP: " + ap + " | Cechy: "
        ));
        const traits = traitsList(w);
        if (traits.length === 0) {
          stats.appendChild(document.createTextNode("-"));
        } else {
          traits.forEach(function (trait, i) {
            stats.appendChild(makeTooltipSpan(trait, i < traits.length - 1 ? ", " : ""));
          });
        }

        line.appendChild(labelWrap);
        line.appendChild(stats);
        list.appendChild(line);
      });
      return;
    }

    // Attack mode — grouped summary
    const filtered = filterWeaponsForMode(weapons, unitState.mode, unitState);
    filtered.forEach((entry) => { entry.activeCount = unitState.weapons[entry.key] || 0; });

    summary.classList.remove("d-none");
    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "text-muted small";
      empty.textContent = "Brak dostępnych ataków w tym trybie.";
      summary.appendChild(empty);
      return;
    }
    const groups = groupAttacks(filtered);
    groups.forEach((g) => {
      const row = document.createElement("div");
      row.className = "attack-summary-row";
      const total = document.createElement("span");
      total.className = "attack-summary-total";
      total.textContent = formatAttacks(g.totalAttacks) + " ataków";
      const meta = document.createElement("span");
      meta.className = "small";
      meta.appendChild(document.createTextNode("AP" + g.ap + " | "));
      if (g.traits.length === 0) {
        meta.appendChild(document.createTextNode("bez cech"));
      } else {
        g.traits.forEach(function (trait, i) {
          meta.appendChild(makeTooltipSpan(trait, i < g.traits.length - 1 ? ", " : ""));
        });
      }
      row.appendChild(total);
      row.appendChild(meta);
      summary.appendChild(row);
    });
  }

  const _weaponsCache = new WeakMap();
  function parseWeaponsCached(card) {
    if (_weaponsCache.has(card)) return _weaponsCache.get(card);
    let weapons = [];
    try { weapons = JSON.parse(card.dataset.weaponsJson || "[]") || []; } catch (e) { weapons = []; }
    _weaponsCache.set(card, weapons);
    return weapons;
  }

  function reorderDefeated(state) {
    const sections = document.querySelectorAll("[data-battle-section]");
    sections.forEach((section) => {
      const wrappers = Array.prototype.slice.call(section.querySelectorAll("[data-battle-card-wrapper]"));
      wrappers.sort((a, b) => {
        const ida = a.querySelector("[data-battle-unit]")?.dataset.rosterUnitId;
        const idb = b.querySelector("[data-battle-unit]")?.dataset.rosterUnitId;
        const da = state.units?.[ida]?.defeated ? 1 : 0;
        const db = state.units?.[idb]?.defeated ? 1 : 0;
        if (da !== db) return da - db;
        return parseInt(a.dataset.originalPosition || 0) - parseInt(b.dataset.originalPosition || 0);
      });
      wrappers.forEach((w) => section.appendChild(w));
    });
  }

  function updateSummaryBadge(state, cards) {
    let active = 0;
    cards.forEach((card) => {
      if (!state.units?.[card.dataset.rosterUnitId]?.defeated) active += 1;
    });
    const a = document.querySelector("[data-active-units]");
    const t = document.querySelector("[data-total-units]");
    if (a) a.textContent = active;
    if (t) t.textContent = cards.length;
  }

  function updateRoundDisplay(state) {
    const el = document.querySelector("[data-round-number]");
    if (el) el.textContent = state.round || 1;
  }

  function applyAbilityStates(card, us) {
    const struck = new Set(us.struckAbilities || []);
    card.querySelectorAll("[data-ability-toggle]").forEach(function (span) {
      span.classList.toggle("is-struck", struck.has(span.dataset.abilityToggle));
    });
  }

  function initTooltips(root) {
    if (typeof bootstrap === "undefined" || !bootstrap.Tooltip) return;
    (root || document).querySelectorAll("[data-bs-toggle='tooltip']").forEach(function (el) {
      if (!bootstrap.Tooltip.getInstance(el)) {
        new bootstrap.Tooltip(el, { trigger: "hover" });
      }
    });
  }

  function init() {
    const root = document.querySelector("[data-battle-root]");
    if (!root) return;
    const rosterId = root.dataset.rosterId;
    const cards = getCards();

    let state = loadState(rosterId) || { units: {}, round: 1 };
    if (!state.units) state.units = {};
    if (!state.round) state.round = 1;

    cards.forEach((card) => {
      const id = card.dataset.rosterUnitId;
      const initial = unitInitialState(card);
      const stored = state.units[id];
      if (!stored) {
        state.units[id] = initial;
      } else {
        // Merge: keep stored values, fill missing fields from initial
        const merged = {
          defeated: !!stored.defeated,
          pinned: !!stored.pinned,
          fatigued: !!stored.fatigued,
          entrenched: !!stored.entrenched,
          activated: !!stored.activated,
          activeModels: typeof stored.activeModels === "number" ? stored.activeModels : initial.activeModels,
          woundsRemaining: typeof stored.woundsRemaining === "number" ? stored.woundsRemaining : initial.woundsRemaining,
          weapons: {},
          primaryOverrides: (stored.primaryOverrides && typeof stored.primaryOverrides === "object") ? stored.primaryOverrides : {},
          mode: stored.mode || "equipment",
          struckAbilities: Array.isArray(stored.struckAbilities) ? stored.struckAbilities : [],
        };
        Object.keys(initial.weapons).forEach((k) => {
          merged.weapons[k] = typeof stored.weapons?.[k] === "number" ? stored.weapons[k] : initial.weapons[k];
        });
        state.units[id] = merged;
      }
      buildModeToolbar(card, parseWeaponsCached(card));
    });

    saveState(rosterId, state);

    function rerenderAll() {
      cards.forEach((card) => {
        const us = state.units[card.dataset.rosterUnitId];
        renderUnit(card, us);
        applyAbilityStates(card, us);
      });
      reorderDefeated(state);
      updateSummaryBadge(state, cards);
      updateRoundDisplay(state);
    }

    function commit() {
      saveState(rosterId, state);
      rerenderAll();
      initTooltips();
    }

    function clamp(value, min, max) {
      if (value < min) return min;
      if (max != null && value > max) return max;
      return value;
    }

    cards.forEach((card) => {
      const id = card.dataset.rosterUnitId;
      const initialModels = parseInt(card.dataset.initialModels || "0", 10) || 0;
      const toughness = parseInt(card.dataset.toughness || "1", 10) || 1;
      const weapons = parseWeaponsCached(card);
      const initialWeaponCounts = {};
      weapons.forEach((w, idx) => {
        const k = weaponKey(w, idx);
        const c = parseInt(w.count, 10);
        initialWeaponCounts[k] = Number.isFinite(c) && c >= 0 ? c : 0;
      });

      card.addEventListener("click", function (ev) {
        // Ability toggle (span click)
        const abilitySpan = ev.target.closest("[data-ability-toggle]");
        if (abilitySpan) {
          const us = state.units[id];
          if (!us) return;
          const label = abilitySpan.dataset.abilityToggle;
          if (!Array.isArray(us.struckAbilities)) us.struckAbilities = [];
          const idx = us.struckAbilities.indexOf(label);
          if (idx >= 0) {
            us.struckAbilities.splice(idx, 1);
          } else {
            us.struckAbilities.push(label);
          }
          commit();
          return;
        }

        // Primary weapon toggle (weapon name click)
        const primaryToggleEl = ev.target.closest("[data-weapon-primary-toggle]");
        if (primaryToggleEl) {
          const us = state.units[id];
          if (!us) return;
          const key = primaryToggleEl.dataset.weaponPrimaryToggle;
          const wIdx = weapons.findIndex((w, i) => weaponKey(w, i) === key);
          if (wIdx < 0) return;
          const w = weapons[wIdx];
          const thisMelee = isMelee(w);
          if (!us.primaryOverrides) us.primaryOverrides = {};
          if (effectiveIsPrimary(w, wIdx, us)) {
            us.primaryOverrides[key] = false;
          } else {
            weapons.forEach((ow, oi) => {
              const ok = weaponKey(ow, oi);
              if (ok !== key && isMelee(ow) === thisMelee && effectiveIsPrimary(ow, oi, us)) {
                us.primaryOverrides[ok] = false;
              }
            });
            us.primaryOverrides[key] = true;
          }
          commit();
          return;
        }

        const target = ev.target.closest("button");
        if (!target) return;
        const us = state.units[id];
        if (!us) return;

        if (target.matches("[data-models-decrement]")) {
          const newCount = clamp(us.activeModels - 1, 0, initialModels);
          if (initialModels > 0) {
            Object.keys(initialWeaponCounts).forEach((k) => {
              us.weapons[k] = Math.round(initialWeaponCounts[k] * newCount / initialModels);
            });
          }
          us.woundsRemaining = clamp(us.woundsRemaining, 0, newCount * toughness);
          us.activeModels = newCount;
          commit();
          return;
        }

        if (target.matches("[data-models-increment]")) {
          const newCount = clamp(us.activeModels + 1, 0, initialModels);
          if (initialModels > 0) {
            Object.keys(initialWeaponCounts).forEach((k) => {
              us.weapons[k] = Math.round(initialWeaponCounts[k] * newCount / initialModels);
            });
          }
          us.activeModels = newCount;
          commit();
          return;
        }

        if (target.matches("[data-wounds-decrement]")) {
          us.woundsRemaining = clamp(us.woundsRemaining - 1, 0, us.activeModels * toughness);
          commit();
          return;
        }

        if (target.matches("[data-wounds-increment]")) {
          us.woundsRemaining = clamp(us.woundsRemaining + 1, 0, us.activeModels * toughness);
          commit();
          return;
        }

        if (target.matches("[data-defeated-toggle]")) {
          us.defeated = !us.defeated;
          commit();
          return;
        }

        const statusKey = target.dataset.statusToggle;
        if (statusKey) {
          const newVal = !us[statusKey];
          us[statusKey] = newVal;
          if (newVal) {
            if (statusKey === "activated") us.entrenched = false;
            else if (statusKey === "entrenched") us.pinned = false;
          }
          commit();
          return;
        }

        const decKey = target.dataset.weaponDecrement;
        if (decKey) {
          const cur = us.weapons[decKey] || 0;
          if (cur <= 0) return;
          us.weapons[decKey] = cur - 1;
          const decIdx = weapons.findIndex((w, i) => weaponKey(w, i) === decKey);
          const thisWeaponDec = weapons[decIdx];
          if (thisWeaponDec && !effectiveIsPrimary(thisWeaponDec, decIdx, us)) {
            const decIsMelee = isMelee(thisWeaponDec);
            weapons.some((w, idx) => {
              if (!effectiveIsPrimary(w, idx, us)) return false;
              if (isMelee(w) !== decIsMelee) return false;
              const pk = weaponKey(w, idx);
              us.weapons[pk] = (us.weapons[pk] || 0) + 1;
              return true;
            });
          }
          commit();
          return;
        }

        const incKey = target.dataset.weaponIncrement;
        if (incKey) {
          const cap = initialWeaponCounts[incKey] || 0;
          const cur = us.weapons[incKey] || 0;
          if (cur >= cap) return;
          us.weapons[incKey] = cur + 1;
          const incIdx = weapons.findIndex((w, i) => weaponKey(w, i) === incKey);
          const thisWeaponInc = weapons[incIdx];
          if (thisWeaponInc && !effectiveIsPrimary(thisWeaponInc, incIdx, us)) {
            const incIsMelee = isMelee(thisWeaponInc);
            weapons.some((w, idx) => {
              if (!effectiveIsPrimary(w, idx, us)) return false;
              if (isMelee(w) !== incIsMelee) return false;
              const pk = weaponKey(w, idx);
              const pcur = us.weapons[pk] || 0;
              if (pcur > 0) { us.weapons[pk] = pcur - 1; return true; }
              return false;
            });
          }
          commit();
          return;
        }

        const mode = target.dataset.mode;
        if (mode) {
          us.mode = mode;
          commit();
          return;
        }
      });
    });

    // End round button
    const endRoundBtn = document.querySelector("[data-battle-end-round]");
    if (endRoundBtn) {
      endRoundBtn.addEventListener("click", function () {
        state.round = (state.round || 1) + 1;
        Object.values(state.units).forEach((us) => { us.activated = false; });
        commit();
      });
    }

    // Reset button
    const resetBtn = document.querySelector("[data-battle-reset]");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        if (!window.confirm("Zakończyć starcie? Stan bitewny zostanie usunięty i przywrócony do wartości początkowych.")) return;
        clearState(rosterId);
        state = { units: {}, round: 1 };
        cards.forEach((card) => { state.units[card.dataset.rosterUnitId] = unitInitialState(card); });
        saveState(rosterId, state);
        rerenderAll();
      });
    }

    rerenderAll();
    initTooltips();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
