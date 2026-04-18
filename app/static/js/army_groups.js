(function () {
  "use strict";

  const root = document.getElementById("army-units-root");
  if (!root) return;
  if (root.getAttribute("data-can-edit") !== "true") return;
  if (typeof Sortable === "undefined") {
    console.warn("[army_groups] SortableJS nie załadowane");
    return;
  }

  const armyId = root.getAttribute("data-army-id");
  const groupsContainer = document.getElementById("army-groups-container");
  const statusEl = document.getElementById("reorder-status");

  // Oznaczamy root klasą po to, by CSS mógł ukryć fallbackowe przyciski ↑↓.
  root.classList.add("js-dnd-enabled");

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.classList.toggle("text-danger", !!isError);
  }

  function collectPayload() {
    const groupSections = Array.from(
      groupsContainer.querySelectorAll(":scope > section.unit-group")
    );
    const buckets = [];
    const groupOrder = [];
    groupSections.forEach((section) => {
      const raw = section.getAttribute("data-group-id");
      const gid = raw ? parseInt(raw, 10) : null;
      groupOrder.push(gid);
      const tbody = section.querySelector(".unit-group-list");
      const unitIds = tbody
        ? Array.from(tbody.querySelectorAll(":scope > tr.unit-row"))
            .map((tr) => parseInt(tr.getAttribute("data-unit-id"), 10))
            .filter((n) => !Number.isNaN(n))
        : [];
      buckets.push({ id: gid, unit_ids: unitIds });
    });
    return { groups: buckets, group_order: groupOrder };
  }

  function sendReorder() {
    const payload = collectPayload();
    setStatus("Zapisuję…");
    return fetch(`/armies/${armyId}/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(() => {
        setStatus("Zapisano ✓");
        setTimeout(() => setStatus(""), 1500);
        refreshPlaceholders();
      })
      .catch((err) => {
        console.error("[army_groups] reorder failed", err);
        setStatus("Błąd zapisu — przeładowuję…", true);
        setTimeout(() => window.location.reload(), 1200);
      });
  }

  function refreshPlaceholders() {
    // Każdy tbody ma placeholder <tr class="empty-placeholder"> gdy pusty.
    groupsContainer.querySelectorAll("tbody.unit-group-list").forEach((tbody) => {
      const hasUnits = tbody.querySelector(":scope > tr.unit-row");
      let placeholder = tbody.querySelector(":scope > tr.empty-placeholder");
      if (!hasUnits && !placeholder) {
        placeholder = document.createElement("tr");
        placeholder.className = "empty-placeholder";
        placeholder.innerHTML =
          '<td colspan="9" class="text-muted small text-center">Przeciągnij tu jednostki…</td>';
        tbody.appendChild(placeholder);
      } else if (hasUnits && placeholder) {
        placeholder.remove();
      }
    });
    // Zaktualizuj licznik w nagłówku grupy.
    groupsContainer.querySelectorAll("section.unit-group").forEach((section) => {
      const count = section.querySelectorAll(
        "tbody.unit-group-list > tr.unit-row"
      ).length;
      const badge = section.querySelector(".unit-count");
      if (badge) badge.textContent = String(count);
    });
  }

  function attachUnitSortable(tbody) {
    Sortable.create(tbody, {
      group: "army-units",
      handle: ".drag-handle",
      animation: 150,
      draggable: "tr.unit-row",
      filter: "tr.empty-placeholder",
      ghostClass: "unit-row-ghost",
      chosenClass: "unit-row-chosen",
      onEnd: sendReorder,
    });
  }

  function attachGroupsSortable() {
    Sortable.create(groupsContainer, {
      handle: ".group-drag-handle",
      animation: 150,
      draggable: "section.unit-group",
      ghostClass: "unit-group-ghost",
      onEnd: sendReorder,
    });
  }

  function attachAllUnitSortables() {
    groupsContainer
      .querySelectorAll("tbody.unit-group-list")
      .forEach(attachUnitSortable);
  }

  // ── Zwijanie ────────────────────────────────────────────────────────────
  groupsContainer.addEventListener("click", function (event) {
    const toggle = event.target.closest(".toggle-collapse, .group-name[data-toggle-group]");
    if (!toggle) return;
    const section = toggle.closest("section.unit-group");
    if (!section) return;
    const body = section.querySelector(".unit-group-body");
    const icon = toggle.querySelector(".collapse-icon");
    const nowCollapsed = !body.classList.contains("d-none");
    body.classList.toggle("d-none", nowCollapsed);
    if (icon) icon.textContent = nowCollapsed ? "▸" : "▾";
    const gidRaw = section.getAttribute("data-group-id");
    if (gidRaw) {
      fetch(`/armies/${armyId}/groups/${gidRaw}/toggle`, {
        method: "POST",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      }).catch(() => {
        /* stan w pamięci już się zmienił; przy kolejnym reloadzie się uspójni */
      });
    }
  });

  // ── Rename grupy (przycisk ✏) ────────────────────────────────────────────
  groupsContainer.addEventListener("click", function (event) {
    const btn = event.target.closest(".rename-group");
    if (!btn) return;
    const gid = btn.getAttribute("data-group-id");
    if (!gid) return;
    const section = btn.closest("section.unit-group");
    const nameSpan = section && section.querySelector(".group-name[data-toggle-group]");
    if (!nameSpan) return;
    const currentName = nameSpan.textContent.trim();

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control form-control-sm";
    input.style.maxWidth = "18rem";
    input.value = currentName;
    nameSpan.replaceWith(input);
    input.focus();
    input.select();

    function commitRename() {
      const newName = input.value.trim();
      if (!newName) {
        input.replaceWith(nameSpan);
        return;
      }
      nameSpan.textContent = newName;
      input.replaceWith(nameSpan);
      const body = new FormData();
      body.append("name", newName);
      fetch(`/armies/${armyId}/groups/${gid}/rename`, {
        method: "POST",
        body: body,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then((res) => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          setStatus("Zapisano nazwę ✓");
          setTimeout(() => setStatus(""), 1200);
        })
        .catch(() => {
          setStatus("Błąd zmiany nazwy", true);
          setTimeout(() => window.location.reload(), 1000);
        });
    }

    function onKeydown(e) {
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") {
        input.removeEventListener("blur", commitRename);
        input.removeEventListener("keydown", onKeydown);
        input.replaceWith(nameSpan);
      }
    }
    input.addEventListener("blur", commitRename);
    input.addEventListener("keydown", onKeydown);
  });

  // ── Usuwanie grupy ──────────────────────────────────────────────────────
  groupsContainer.addEventListener("click", function (event) {
    const btn = event.target.closest(".delete-group");
    if (!btn) return;
    const gid = btn.getAttribute("data-group-id");
    if (!gid) return;
    if (
      !window.confirm(
        "Usunąć grupę? Jednostki zostaną przeniesione do sekcji «Bez grupy»."
      )
    ) {
      return;
    }
    fetch(`/armies/${armyId}/groups/${gid}/delete`, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        // Przeładuj dla pewności spójności DOM z bazą.
        window.location.reload();
      })
      .catch(() => {
        setStatus("Błąd usuwania grupy", true);
        setTimeout(() => window.location.reload(), 1000);
      });
  });

  // ── Dodawanie grupy ─────────────────────────────────────────────────────
  const addBtn = document.getElementById("btn-add-group");
  const addInput = document.getElementById("new-group-name");
  function submitNewGroup() {
    if (!addInput) return;
    const name = (addInput.value || "").trim();
    if (!name) {
      addInput.focus();
      return;
    }
    const body = new FormData();
    body.append("name", name);
    fetch(`/armies/${armyId}/groups`, {
      method: "POST",
      body: body,
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(() => {
        window.location.reload();
      })
      .catch(() => {
        setStatus("Nie udało się dodać grupy", true);
      });
  }
  if (addBtn) addBtn.addEventListener("click", submitNewGroup);
  if (addInput) {
    addInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        submitNewGroup();
      }
    });
  }

  // ── Inicjalizacja Sortable ──────────────────────────────────────────────
  attachAllUnitSortables();
  attachGroupsSortable();
  refreshPlaceholders();
})();
