(function () {
  "use strict";

  const STORAGE_PREFIX = "opr.battleState.";
  const MELEE_ASSAULT_TRAITS = new Set(["szturmowy", "szturmowa", "assault"]);
  const UNWIELDY_TRAITS = new Set(["nieporeczna", "unwieldy"]);

  function normalizeSlug(value) {
    if (value == null) return "";
    let text = String(value).trim().toLowerCase();
    if (text.normalize) {
      text = text.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
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

  function traitsList(weapon) {
    if (Array.isArray(weapon.traits_list)) return weapon.traits_list;
    const raw = weapon.traits;
    if (!raw) return [];
    return String(raw)
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
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
      console.warn("battle_state: failed to load state", e);
      return null;
    }
  }

  function saveState(rosterId, state) {
    try {
      window.localStorage.setItem(storageKey(rosterId), JSON.stringify(state));
    } catch (e) {
      console.warn("battle_state: failed to save state", e);
    }
  }

  function clearState(rosterId) {
    try {
      window.localStorage.removeItem(storageKey(rosterId));
    } catch (e) {
      /* noop */
    }
  }

  function unitInitialState(card) {
    const initialModels = parseInt(card.dataset.initialModels || "0", 10) || 0;
    let weapons = [];
    try {
      weapons = JSON.parse(card.dataset.weaponsJson || "[]") || [];
    } catch (e) {
      weapons = [];
    }
    const weaponCounts = {};
    weapons.forEach((w, idx) => {
      const key = weaponKey(w, idx);
      const c = parseInt(w.count, 10);
      weaponCounts[key] = Number.isFinite(c) && c >= 0 ? c : 0;
    });
    return {
      defeated: false,
      activeModels: initialModels,
      weapons: weaponCounts,
      mode: "equipment",
    };
  }

  function weaponKey(weapon, idx) {
    if (weapon.weapon_id != null) return "w" + weapon.weapon_id;
    return "i" + idx;
  }

  function getCards() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-battle-unit]")
    );
  }

  function buildModeToolbar(card, weapons) {
    const toolbar = card.querySelector("[data-mode-toolbar]");
    if (!toolbar) return;
    // Remove dynamic range buttons (keep equipment + melee)
    toolbar
      .querySelectorAll("[data-mode^='ranged:']")
      .forEach((b) => b.remove());

    const ranges = new Set();
    weapons.forEach((w) => {
      const r = parseRangeInt(w);
      if (r > 0) ranges.add(r);
    });
    const sorted = Array.from(ranges).sort((a, b) => a - b);
    sorted.forEach((r) => {
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
      // Always strip assault traits from grouping key and display
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

  function formatAp(ap) {
    return "AP" + ap;
  }

  function renderUnit(card, unitState) {
    const weapons = parseWeaponsCached(card);

    // Header counters
    const modelsValue = card.querySelector("[data-models-value]");
    if (modelsValue) modelsValue.textContent = unitState.activeModels;

    // Defeated state
    if (unitState.defeated) {
      card.classList.add("is-defeated");
      const lblA = card.querySelector("[data-defeated-label-active]");
      const lblI = card.querySelector("[data-defeated-label-inactive]");
      if (lblA) lblA.classList.add("d-none");
      if (lblI) lblI.classList.remove("d-none");
    } else {
      card.classList.remove("is-defeated");
      const lblA = card.querySelector("[data-defeated-label-active]");
      const lblI = card.querySelector("[data-defeated-label-inactive]");
      if (lblA) lblA.classList.remove("d-none");
      if (lblI) lblI.classList.add("d-none");
    }

    // Mode toolbar buttons (active state)
    const toolbar = card.querySelector("[data-mode-toolbar]");
    if (toolbar) {
      toolbar.querySelectorAll("[data-mode]").forEach((btn) => {
        if (btn.dataset.mode === unitState.mode) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    }

    // Render weapon list
    const list = card.querySelector("[data-weapon-list]");
    const summary = card.querySelector("[data-attack-summary]");
    if (!list || !summary) return;

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
        labelWrap.className = "d-flex align-items-center gap-1 flex-grow-1";
        labelWrap.style.flex = "1 1 100%";

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
        labelText.textContent = w.name || "Broń";

        labelWrap.appendChild(dec);
        labelWrap.appendChild(valueSpan);
        labelWrap.appendChild(initialSpan);
        labelWrap.appendChild(inc);
        labelWrap.appendChild(labelText);

        const stats = document.createElement("span");
        stats.className = "weapon-stats";
        const range = parseRangeInt(w);
        const attacks = w.attacks == null || w.attacks === "" ? "-" : w.attacks;
        const ap = w.ap == null ? "-" : w.ap;
        const tr = (w.traits || "-") || "-";
        stats.textContent =
          "Ataki: " + attacks + " | Zasięg: " + (range || "wręcz") + " | AP: " + ap + " | Cechy: " + tr;

        line.appendChild(labelWrap);
        line.appendChild(stats);
        list.appendChild(line);
      });
      return;
    }

    // Attack mode (melee or ranged:R) — show grouped summary
    const filtered = filterWeaponsForMode(weapons, unitState.mode, unitState);
    filtered.forEach((entry) => {
      entry.activeCount = unitState.weapons[entry.key] || 0;
    });

    if (filtered.length === 0) {
      summary.classList.remove("d-none");
      const empty = document.createElement("div");
      empty.className = "text-muted small";
      empty.textContent = "Brak dostępnych ataków w tym trybie.";
      summary.appendChild(empty);
      return;
    }

    summary.classList.remove("d-none");
    const groups = groupAttacks(filtered);
    groups.forEach((g) => {
      const row = document.createElement("div");
      row.className = "attack-summary-row";

      const total = document.createElement("span");
      total.className = "attack-summary-total";
      total.textContent = formatAttacks(g.totalAttacks) + " ataków";

      const meta = document.createElement("span");
      meta.className = "small";
      const traitsText = g.traits.length ? g.traits.join(", ") : "bez cech";
      meta.textContent = formatAp(g.ap) + " | " + traitsText;

      row.appendChild(total);
      row.appendChild(meta);
      summary.appendChild(row);
    });
  }

  const _weaponsCache = new WeakMap();
  function parseWeaponsCached(card) {
    if (_weaponsCache.has(card)) return _weaponsCache.get(card);
    let weapons = [];
    try {
      weapons = JSON.parse(card.dataset.weaponsJson || "[]") || [];
    } catch (e) {
      weapons = [];
    }
    _weaponsCache.set(card, weapons);
    return weapons;
  }

  function reorderDefeated(state) {
    const sections = document.querySelectorAll("[data-battle-section]");
    sections.forEach((section) => {
      const wrappers = Array.prototype.slice.call(
        section.querySelectorAll("[data-battle-card-wrapper]")
      );
      wrappers.sort((a, b) => {
        const ca = a.querySelector("[data-battle-unit]");
        const cb = b.querySelector("[data-battle-unit]");
        const ida = ca && ca.dataset.rosterUnitId;
        const idb = cb && cb.dataset.rosterUnitId;
        const da = (state.units && state.units[ida] && state.units[ida].defeated) ? 1 : 0;
        const db = (state.units && state.units[idb] && state.units[idb].defeated) ? 1 : 0;
        if (da !== db) return da - db;
        // restore original roster position within same group (active or defeated)
        return parseInt(a.dataset.originalPosition || 0) - parseInt(b.dataset.originalPosition || 0);
      });
      wrappers.forEach((w) => section.appendChild(w));
    });
  }

  function updateSummaryBadge(state) {
    const cards = getCards();
    const total = cards.length;
    let active = 0;
    cards.forEach((card) => {
      const id = card.dataset.rosterUnitId;
      const us = state.units[id];
      if (!us || !us.defeated) active += 1;
    });
    const a = document.querySelector("[data-active-units]");
    const t = document.querySelector("[data-total-units]");
    if (a) a.textContent = active;
    if (t) t.textContent = total;
  }

  function init() {
    const root = document.querySelector("[data-battle-root]");
    if (!root) return;
    const rosterId = root.dataset.rosterId;

    const cards = getCards();
    let state = loadState(rosterId) || { units: {} };
    if (!state.units) state.units = {};

    cards.forEach((card) => {
      const id = card.dataset.rosterUnitId;
      const initial = unitInitialState(card);
      // Merge stored state but keep weapon keys consistent with current data
      const stored = state.units[id];
      if (!stored) {
        state.units[id] = initial;
      } else {
        // Merge weapons — only keep keys that exist now
        const merged = {
          defeated: !!stored.defeated,
          activeModels:
            typeof stored.activeModels === "number"
              ? stored.activeModels
              : initial.activeModels,
          weapons: {},
          mode: stored.mode || "equipment",
        };
        Object.keys(initial.weapons).forEach((k) => {
          merged.weapons[k] =
            stored.weapons && typeof stored.weapons[k] === "number"
              ? stored.weapons[k]
              : initial.weapons[k];
        });
        state.units[id] = merged;
      }
      const weapons = parseWeaponsCached(card);
      buildModeToolbar(card, weapons);
    });

    saveState(rosterId, state);

    function rerenderAll() {
      cards.forEach((card) => {
        const id = card.dataset.rosterUnitId;
        renderUnit(card, state.units[id]);
      });
      reorderDefeated(state);
      updateSummaryBadge(state);
    }

    function commit() {
      saveState(rosterId, state);
      rerenderAll();
    }

    function clamp(value, min, max) {
      if (value < min) return min;
      if (max != null && value > max) return max;
      return value;
    }

    cards.forEach((card) => {
      const id = card.dataset.rosterUnitId;
      const initialModels = parseInt(card.dataset.initialModels || "0", 10) || 0;
      const weapons = parseWeaponsCached(card);
      const initialWeaponCounts = {};
      weapons.forEach((w, idx) => {
        const k = weaponKey(w, idx);
        const c = parseInt(w.count, 10);
        initialWeaponCounts[k] = Number.isFinite(c) && c >= 0 ? c : 0;
      });

      card.addEventListener("click", function (ev) {
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
        if (target.matches("[data-defeated-toggle]")) {
          us.defeated = !us.defeated;
          commit();
          return;
        }
        const decKey = target.dataset.weaponDecrement;
        if (decKey) {
          const cap = initialWeaponCounts[decKey] || 0;
          const cur = us.weapons[decKey] || 0;
          us.weapons[decKey] = clamp(cur - 1, 0, cap);
          commit();
          return;
        }
        const incKey = target.dataset.weaponIncrement;
        if (incKey) {
          const cap = initialWeaponCounts[incKey] || 0;
          const cur = us.weapons[incKey] || 0;
          us.weapons[incKey] = clamp(cur + 1, 0, cap);
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

    const resetBtn = document.querySelector("[data-battle-reset]");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        const ok = window.confirm(
          "Zakończyć starcie? Stan bitewny zostanie usunięty i przywrócony do wartości początkowych."
        );
        if (!ok) return;
        clearState(rosterId);
        state = { units: {} };
        cards.forEach((card) => {
          const cid = card.dataset.rosterUnitId;
          state.units[cid] = unitInitialState(card);
        });
        saveState(rosterId, state);
        rerenderAll();
      });
    }

    rerenderAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
