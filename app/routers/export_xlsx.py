from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs
from .rosters import _ensure_roster_view_access, _roster_unit_export_data


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


def _weapon_details_text(details: list[dict[str, Any]]) -> str:
    if not details:
        return "-"
    lines: list[str] = []
    for weapon in details:
        name = weapon.get("name") or "Broń"
        count = weapon.get("count") or 0
        range_value = weapon.get("range") or "-"
        attacks = weapon.get("attacks") or "-"
        ap_value = weapon.get("ap") if weapon.get("ap") is not None else "-"
        traits = weapon.get("traits") or "-"
        lines.append(
            f"{name} × {count} | Z: {range_value} | Ataki: {attacks} | AP: {ap_value} | Cechy: {traits}"
        )
    return "\n".join(lines)


def _append_roster_sheet(
    workbook: Workbook,
    entries: list[dict[str, Any]],
) -> float:
    sheet = workbook.active
    sheet.title = "Lista"
    sheet.append(
        [
            "Jednostka",
            "Oddział",
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
    for entry in entries:
        total_value = float(entry.get("total_cost", 0.0))
        total_cost += total_value
        sheet.append(
            [
                entry.get("unit_name"),
                entry.get("custom_name") or "",
                entry.get("count"),
                entry.get("quality"),
                entry.get("defense"),
                entry.get("toughness"),
                _abilities_text(
                    entry.get("passive_labels", []),
                    entry.get("active_labels", []),
                    entry.get("aura_labels", []),
                ),
                _weapon_details_text(entry.get("weapon_details", [])),
                round(total_value, 2),
            ]
        )

    sheet.append(["", "", "", "", "", "", "Razem", "", round(total_cost, 2)])
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        adjusted = max_length + 2
        column_letter = column_cells[0].column_letter
        sheet.column_dimensions[column_letter].width = min(adjusted, 60)
    return total_cost


def _append_weapons_sheet(workbook: Workbook, entries: list[dict[str, Any]]) -> None:
    sheet = workbook.create_sheet("Zbrojownia")
    sheet.append(["Nazwa", "Ilość", "Zasięg", "Ataki", "AP", "Cechy"])
    aggregated: dict[tuple[str, str, str, str, str], int] = {}
    for entry in entries:
        for weapon in entry.get("weapon_details", []):
            name = weapon.get("name") or "Broń"
            range_value = weapon.get("range") or "-"
            attacks = str(weapon.get("attacks") or "-")
            ap_value = (
                str(weapon.get("ap")) if weapon.get("ap") is not None else "-"
            )
            traits = weapon.get("traits") or "-"
            key = (name, str(range_value), attacks, ap_value, traits)
            aggregated[key] = aggregated.get(key, 0) + int(weapon.get("count") or 0)
    for (name, range_value, attacks, ap_value, traits), count in sorted(aggregated.items()):
        sheet.append([name, count, range_value, attacks, ap_value, traits])
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
    entries = [_roster_unit_export_data(ru) for ru in roster.roster_units]
    total_cost = _append_roster_sheet(workbook, entries)
    _append_weapons_sheet(workbook, entries)

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

