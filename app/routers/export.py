from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..services import costs
from .rosters import _ensure_roster_access

router = APIRouter(prefix="/rosters", tags=["export"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{roster_id}/print", response_class=HTMLResponse)
def roster_print(
    roster_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    return templates.TemplateResponse(
        "roster_print.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
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
    roster = db.get(models.Roster, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_access(roster, current_user)

    costs.update_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)

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
    for ru in roster.roster_units:
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(40, y, "Jednostka")
            pdf.drawString(280, y, "Ilość")
            pdf.drawString(340, y, "Koszt")
            y -= 20
            pdf.setFont("Helvetica", 11)
        pdf.drawString(40, y, f"{ru.unit.name} ({ru.count}x)")
        pdf.drawString(280, y, str(ru.count))
        pdf.drawString(340, y, f"{ru.cached_cost or costs.roster_unit_cost(ru):.1f}")
        y -= 16

    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, f"Suma: {total_cost:.1f} pkt")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    headers = {"Content-Disposition": f"attachment; filename=roster_{roster_id}.pdf"}
    return Response(buffer.getvalue(), media_type="application/pdf", headers=headers)
