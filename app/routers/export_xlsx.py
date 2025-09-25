from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs
from .rosters import (
    _ability_entries,
    _default_loadout_summary,
    _ensure_roster_view_access,
    _loadout_display_summary,
    _passive_labels,
    _roster_unit_loadout,
    _unit_weapon_options,
)


router = APIRouter(prefix="/export", tags=["export"])


def _abilities_text(passives: list[str], actives: list[str], auras: list[str]) -> str:
    parts: list[str] = []
    if passives:
        parts.append(f"Pasywne: {', '.join(passives)}")
    if actives:
        parts.append(f"Aktywne: {', '.join(actives)}")
    if auras:
        parts.append(f"Aury: {', '.join(auras)}")
    return "\n".join(parts) if parts else "-"


def _append_roster_sheet(workbook: Workbook, roster: models.Roster) -> float:
    sheet = workbook.active
    sheet.title = "Lista"
    sheet.append(
        [
            "Jednostka",
            "Ilość",
            "Jakość",
            "Obrona",
            "Wytrzymałość",
            "Zdolności",
            "Uzbrojenie",
            "Suma [pkt]",
        ]
    )

    total_cost = 0.0
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        passive_labels = _passive_labels(unit)
        active_items = _ability_entries(unit, "active")
        aura_items = _ability_entries(unit, "aura")
        active_labels = [item.get("label") for item in active_items if item.get("label")]
        aura_labels = [item.get("label") for item in aura_items if item.get("label")]
        weapon_options = _unit_weapon_options(unit)
        loadout = _roster_unit_loadout(
            roster_unit,
            weapon_options=weapon_options,
            active_items=active_items,
            aura_items=aura_items,
        )
        weapon_summary = _loadout_display_summary(roster_unit, loadout, weapon_options)
        if not weapon_summary:
            weapon_summary = _default_loadout_summary(unit)
        total_value = float(roster_unit.cached_cost or costs.roster_unit_cost(roster_unit))
        total_cost += total_value
        sheet.append(
            [
                unit.name,
                roster_unit.count,
                unit.quality,
                unit.defense,
                unit.toughness,
                _abilities_text(passive_labels, active_labels, aura_labels),
                weapon_summary,
                round(total_value, 2),
            ]
        )

    sheet.append(["", "", "", "", "", "Razem", "", round(total_cost, 2)])
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        adjusted = max_length + 2
        column_letter = column_cells[0].column_letter
        sheet.column_dimensions[column_letter].width = min(adjusted, 60)
    return total_cost


def _append_weapons_sheet(workbook: Workbook, roster: models.Roster) -> None:
    sheet = workbook.create_sheet("Zbrojownia")
    sheet.append(["Nazwa", "Zasięg", "Ataki", "AP", "Cechy"])
    used: dict[str, tuple[str, str, str, str]] = {}
    for roster_unit in roster.roster_units:
        if roster_unit.selected_weapon:
            weapons = [roster_unit.selected_weapon]
        else:
            weapons = costs.unit_default_weapons(roster_unit.unit)
        for weapon in weapons:
            if not weapon:
                continue
            name = weapon.effective_name or weapon.name or "Broń"
            if name in used:
                continue
            attacks = getattr(weapon, "display_attacks", None)
            if attacks is None:
                attacks = weapon.effective_attacks
            traits = weapon.effective_tags or weapon.tags or ""
            used[name] = (
                weapon.effective_range or weapon.range or "-",
                str(attacks),
                str(weapon.effective_ap if hasattr(weapon, "effective_ap") else weapon.ap or 0),
                traits,
            )
    for name in sorted(used):
        sheet.append([name, *used[name]])
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        adjusted = max_length + 2
        column_letter = column_cells[0].column_letter
        sheet.column_dimensions[column_letter].width = min(adjusted, 50)


@router.get("/xlsx/{roster_id}")
def export_xlsx(
    roster_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if current_user is None:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    workbook = Workbook()
    total_cost = _append_roster_sheet(workbook, roster)
    _append_weapons_sheet(workbook, roster)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"roster_{roster_id}_{int(round(total_cost))}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

