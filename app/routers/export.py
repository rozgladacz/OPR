from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import ability_registry, costs
from .rosters import (
    _default_loadout_summary,
    _ensure_roster_view_access,
    _passive_labels,
)

router = APIRouter(prefix="/rosters", tags=["export"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{roster_id}/print", response_class=HTMLResponse)
def roster_print(
    roster_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    roster_items = []
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        passive_labels = _passive_labels(unit)
        active_labels = [
            item.get("label") or item.get("raw") or ""
            for item in ability_registry.unit_ability_payload(unit, "active")
        ]
        aura_labels = [
            item.get("label") or item.get("raw") or ""
            for item in ability_registry.unit_ability_payload(unit, "aura")
        ]
        roster_items.append(
            {
                "instance": roster_unit,
                "passive_labels": passive_labels,
                "active_labels": active_labels,
                "aura_labels": aura_labels,
                "default_summary": _default_loadout_summary(unit),
            }
        )
    return templates.TemplateResponse(
        "roster_print.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "roster_items": roster_items,
            "total_cost": total_cost,
            "generated_at": datetime.utcnow(),
        },
    )


@router.get("/{roster_id}/pdf")
def roster_pdf(
    roster_id: int,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    roster_items = []
    for roster_unit in roster.roster_units:
        unit = roster_unit.unit
        passive_labels = _passive_labels(unit)
        active_labels = [
            item.get("label") or item.get("raw") or ""
            for item in ability_registry.unit_ability_payload(unit, "active")
        ]
        aura_labels = [
            item.get("label") or item.get("raw") or ""
            for item in ability_registry.unit_ability_payload(unit, "aura")
        ]
        roster_items.append(
            {
                "instance": roster_unit,
                "passive_labels": passive_labels,
                "active_labels": active_labels,
                "aura_labels": aura_labels,
                "default_summary": _default_loadout_summary(unit),
            }
        )

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, f"Rozpiska: {roster.name}")
    y -= 20
    pdf.setFont("Helvetica", 12)
    pdf.drawString(40, y, f"Armia: {roster.army.name}")
    y -= 20
    pdf.drawString(40, y, f"Limit punktów: {roster.points_limit or 'brak'}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Jednostka")
    pdf.drawString(280, y, "Ilość")
    pdf.drawString(340, y, "Koszt")
    y -= 20

    pdf.setFont("Helvetica", 11)
    line_height = 16
    for item in roster_items:
        ru = item["instance"]
        abilities_text = []
        if item["passive_labels"]:
            abilities_text.append(f"Pasywne: {', '.join(item['passive_labels'])}")
        if item["active_labels"]:
            abilities_text.append(f"Aktywne: {', '.join(item['active_labels'])}")
        if item["aura_labels"]:
            abilities_text.append(f"Aury: {', '.join(item['aura_labels'])}")
        required_space = 80 + line_height * (len(abilities_text) + 2)
        if y < required_space:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(40, y, "Jednostka")
            pdf.drawString(280, y, "Ilość")
            pdf.drawString(340, y, "Koszt")
            y -= 20
            pdf.setFont("Helvetica", 11)
        weapon_label = (
            ru.selected_weapon.effective_name
            if ru.selected_weapon
            else item["default_summary"]
        )
        pdf.drawString(40, y, f"{ru.unit.name} ({ru.count}x)")
        pdf.drawString(280, y, str(ru.count))
        pdf.drawString(340, y, f"{ru.cached_cost or costs.roster_unit_cost(ru):.1f}")
        y -= line_height
        pdf.drawString(40, y, f"Uzbrojenie: {weapon_label}")
        y -= line_height
        for ability_line in abilities_text:
            pdf.drawString(40, y, ability_line)
            y -= line_height
        y -= 4

    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, f"Suma: {total_cost:.1f} pkt")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    headers = {"Content-Disposition": f"attachment; filename=roster_{roster_id}.pdf"}
    return Response(buffer.getvalue(), media_type="application/pdf", headers=headers)
