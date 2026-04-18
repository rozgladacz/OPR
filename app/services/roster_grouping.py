"""Grupowanie pozycji rozpiski wg grup zdefiniowanych w armii.

Rozpiska dziedziczy grupy ze źródłowych ``Unit.group``. Jeżeli armia nie ma
żadnej grupy, zwracamy pojedynczą sekcję bez nagłówka (group=None).
"""

from __future__ import annotations

from typing import Any, Iterable


def _roster_unit_of(item: Any):
    if isinstance(item, dict):
        return item.get("instance")
    return getattr(item, "instance", None)


def group_available_units(
    available_units: Iterable[Any],
    army,
) -> list[dict[str, Any]]:
    """Zwraca sekcje dla panelu 'Jednostki w armii': [{"group": UnitGroup|None, "units": [...]}].

    Każdy element available_units to dict z kluczem ``"unit"``.
    """
    items = list(available_units)
    groups = sorted(
        list(getattr(army, "unit_groups", []) or []),
        key=lambda g: (getattr(g, "position", 0), getattr(g, "id", 0)),
    )
    valid_ids = {g.id for g in groups}
    buckets: dict[int | None, list[Any]] = {g.id: [] for g in groups}
    buckets[None] = []
    for item in items:
        unit = item.get("unit") if isinstance(item, dict) else getattr(item, "unit", None)
        group_id = getattr(unit, "group_id", None) if unit is not None else None
        key = group_id if group_id in valid_ids else None
        buckets[key].append(item)
    sections: list[dict[str, Any]] = []
    for group in groups:
        if buckets.get(group.id):
            sections.append({"group": group, "units": buckets[group.id]})
    if buckets[None]:
        sections.append({"group": None, "units": buckets[None]})
    return sections


def group_roster_items(
    roster_items: Iterable[Any],
    army,
) -> list[dict[str, Any]]:
    """Zwraca listę sekcji: [{"group": UnitGroup|None, "units": [...]}].

    Kolejność sekcji odpowiada ``UnitGroup.position`` w armii. Puste grupy
    są pomijane. Element bez rozpoznanej grupy trafia do sekcji "Bez grupy"
    (``group=None``) dodanej na końcu, tylko jeśli zawiera pozycje.
    """

    items = list(roster_items)
    groups = sorted(
        list(getattr(army, "unit_groups", []) or []),
        key=lambda g: (getattr(g, "position", 0), getattr(g, "id", 0)),
    )
    valid_ids = {g.id for g in groups}

    buckets: dict[int | None, list[Any]] = {g.id: [] for g in groups}
    buckets[None] = []

    for item in items:
        roster_unit = _roster_unit_of(item)
        unit = getattr(roster_unit, "unit", None) if roster_unit is not None else None
        group_id = getattr(unit, "group_id", None) if unit is not None else None
        key = group_id if group_id in valid_ids else None
        buckets[key].append(item)

    sections: list[dict[str, Any]] = []
    for group in groups:
        section_items = buckets.get(group.id, [])
        if section_items:
            sections.append({"group": group, "units": section_items})
    tail = buckets.get(None, [])
    if tail:
        sections.append({"group": None, "units": tail})

    # Jeżeli armia nie ma grup w ogóle i brak tailu (niemożliwe w praktyce,
    # ale dla pewności): zwracamy pustą listę. Szablon może wtedy spaść na
    # stary render po ``roster_items``.
    return sections
