from __future__ import annotations

import base64
import binascii
import io
import textwrap
from datetime import datetime
import zlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..db import get_db
from ..security import get_current_user
from ..pdf_font_data import PDF_FONT_DATA
from ..services import costs, utils
from .rosters import (
    _classification_map,
    _ensure_roster_view_access,
    _roster_unit_export_data,
    _roster_unit_loadout,
)

router = APIRouter(prefix="/rosters", tags=["export"])
templates = Jinja2Templates(directory="app/templates")

PDF_BASE_FONT = "DejaVuSans"
PDF_BOLD_FONT = "DejaVuSans-Bold"
PDF_ITALIC_FONT = "DejaVuSans"
_PDF_FONTS_REGISTERED = False
_PDF_FONT_BYTES: dict[str, bytes] = {}


def _army_spell_entries(
    roster: models.Roster, unit_entries: list[dict[str, object]]
) -> list[dict[str, object]]:
    army = getattr(roster, "army", None)
    if not army:
        return []
    has_mag = False
    for entry in unit_entries:
        slugs = entry.get("active_slugs") if isinstance(entry, dict) else None
        if not slugs:
            continue
        for slug in slugs:
            if str(slug).strip().casefold() == "mag":
                has_mag = True
                break
        if has_mag:
            break
    if not has_mag:
        return []
    spells = getattr(army, "spells", []) or []
    result: list[dict[str, object]] = []
    for spell in spells:
        payload = getattr(spell, "export_payload", None)
        if not payload:
            continue
        label = (payload.get("label") or "").strip()
        if not label:
            continue
        entry = {
            "cost": int(payload.get("cost") or 0),
            "label": label,
            "description": (payload.get("description") or "").strip(),
        }
        result.append(entry)
    return result


def _army_rule_labels(army: models.Army | None) -> list[str]:
    labels: list[str] = []
    for entry in costs.army_rules(army=army):
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug or slug.startswith(utils.ARMY_RULE_OFF_PREFIX):
            continue
        label = entry.get("label") or entry.get("value") or slug
        text = str(label).strip()
        if text:
            labels.append(text)
    return labels


def _ensure_pdf_fonts() -> None:
    global _PDF_FONTS_REGISTERED
    if _PDF_FONTS_REGISTERED:
        return
    def _font_bytes(font_name: str) -> bytes:
        cached = _PDF_FONT_BYTES.get(font_name)
        if cached is not None:
            return cached
        encoded = PDF_FONT_DATA.get(font_name)
        if not encoded:
            raise HTTPException(
                status_code=500,
                detail="Brak zdefiniowanych danych czcionki wymaganej do eksportu PDF.",
            )
        try:
            compressed = base64.b64decode(encoded)
            raw = zlib.decompress(compressed)
        except (binascii.Error, zlib.error):
            raise HTTPException(
                status_code=500,
                detail="Nie udało się przygotować czcionek dla eksportu PDF.",
            )
        _PDF_FONT_BYTES[font_name] = raw
        return raw

    regular_bytes = _font_bytes(PDF_BASE_FONT)
    bold_bytes = _font_bytes(PDF_BOLD_FONT)
    registered = set(pdfmetrics.getRegisteredFontNames())
    if PDF_BASE_FONT not in registered:
        pdfmetrics.registerFont(TTFont(PDF_BASE_FONT, io.BytesIO(regular_bytes)))
    if PDF_BOLD_FONT not in registered:
        pdfmetrics.registerFont(TTFont(PDF_BOLD_FONT, io.BytesIO(bold_bytes)))
    pdfmetrics.registerFontFamily(
        PDF_BASE_FONT,
        normal=PDF_BASE_FONT,
        bold=PDF_BOLD_FONT,
        italic=PDF_ITALIC_FONT,
        boldItalic=PDF_BOLD_FONT,
    )
    _PDF_FONTS_REGISTERED = True


def _load_roster_for_export(db: Session, roster_id: int) -> models.Roster | None:
    stmt = (
        select(models.Roster)
        .where(models.Roster.id == roster_id)
        .options(
            selectinload(models.Roster.roster_units).options(
                selectinload(models.RosterUnit.unit).options(
                    selectinload(models.Unit.weapon_links)
                    .selectinload(models.UnitWeapon.weapon)
                    .selectinload(models.Weapon.parent)
                    .selectinload(models.Weapon.parent),
                    selectinload(models.Unit.default_weapon)
                    .selectinload(models.Weapon.parent)
                    .selectinload(models.Weapon.parent),
                    selectinload(models.Unit.abilities).selectinload(
                        models.UnitAbility.ability
                    ),
                    selectinload(models.Unit.army),
                )
            ),
            selectinload(models.Roster.army).selectinload(models.Army.spells),
        )
    )
    return db.scalars(stmt).one_or_none()


def _export_roster_unit_entries(
    db: Session, roster: models.Roster
) -> list[dict[str, Any]]:
    unit_cache: dict[int, dict[str, Any]] = {}
    loadouts: dict[int, dict[str, Any]] = {}
    for roster_unit in roster.roster_units:
        unit_id = getattr(roster_unit, "id", None)
        if unit_id is None:
            continue
        loadouts[unit_id] = _roster_unit_loadout(roster_unit)
    classifications, _totals = _classification_map(
        roster.roster_units, loadouts
    )
    entries: list[dict[str, Any]] = []
    for roster_unit in roster.roster_units:
        unit_id = getattr(roster_unit, "id", None)
        entries.append(
            _roster_unit_export_data(
                roster_unit,
                unit_cache=unit_cache,
                loadout_override=loadouts.get(unit_id),
                classification=classifications.get(unit_id),
            )
        )
    return entries


@router.get("/{roster_id}/print", response_class=HTMLResponse)
def roster_print(
    roster_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster = _load_roster_for_export(db, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    costs.ensure_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    total_cost_rounded = utils.round_points(total_cost)
    roster_items = _export_roster_unit_entries(db, roster)
    spell_entries = _army_spell_entries(roster, roster_items)
    army_rules = _army_rule_labels(getattr(roster, "army", None))
    return templates.TemplateResponse(
        "roster_print.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "roster_items": roster_items,
            "total_cost": total_cost,
            "total_cost_rounded": total_cost_rounded,
            "generated_at": datetime.utcnow(),
            "spell_entries": spell_entries,
            "army_rules": army_rules,
        },
    )


@router.get("/{roster_id}/export/lista", response_class=HTMLResponse)
def roster_export_list(
    roster_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user(optional=True)),
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)
    roster = _load_roster_for_export(db, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    costs.ensure_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    total_cost_rounded = utils.round_points(total_cost)

    entries = _export_roster_unit_entries(db, roster)
    spell_entries = _army_spell_entries(roster, entries)
    army_rules = _army_rule_labels(getattr(roster, "army", None))

    return templates.TemplateResponse(
        "export/lista.html",
        {
            "request": request,
            "user": current_user,
            "roster": roster,
            "entries": entries,
            "total_cost": total_cost,
            "total_cost_rounded": total_cost_rounded,
            "generated_at": datetime.utcnow(),
            "spell_entries": spell_entries,
            "army_rules": army_rules,
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
    roster = _load_roster_for_export(db, roster_id)
    if not roster:
        raise HTTPException(status_code=404)
    _ensure_roster_view_access(roster, current_user)

    generated_at = datetime.utcnow()
    costs.ensure_cached_costs(roster.roster_units)
    total_cost = costs.roster_total(roster)
    total_cost_rounded = utils.round_points(total_cost)
    roster_items = _export_roster_unit_entries(db, roster)
    spell_entries = _army_spell_entries(roster, roster_items)

    _ensure_pdf_fonts()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    line_height = 12
    margin = 60

    def wrap_line(text: str, width_limit: int = 110) -> list[str]:
        if not text:
            return [""]
        wrapped = textwrap.wrap(text, width=width_limit)
        return wrapped or [text]

    def draw_page_header() -> None:
        nonlocal y
        pdf.setFont(PDF_BOLD_FONT, 14)
        pdf.drawString(40, y, f"Rozpiska: {roster.name}")
        y -= 16
        pdf.setFont(PDF_BASE_FONT, 10)
        army_name = roster.army.name if roster.army else "---"
        pdf.drawString(40, y, f"Armia: {army_name}")
        y -= 14
        pdf.drawString(40, y, f"Limit punktów: {roster.points_limit or 'brak'}")
        y -= 14
        pdf.drawString(40, y, f"Suma punktów: {total_cost_rounded} pkt")
        y -= 14
        pdf.drawString(40, y, f"Wygenerowano: {generated_at.strftime('%Y-%m-%d %H:%M')} UTC")
        y -= 14
        if army_rules:
            rule_line = f"Zasady armii: {', '.join(army_rules)}"
            for segment in wrap_line(rule_line):
                pdf.drawString(40, y, segment)
                y -= 14
        y -= 4
        pdf.setFont(PDF_BASE_FONT, 10)

    draw_page_header()

    for item in roster_items:
        name = item.get("custom_name") or item.get("unit_name") or "Jednostka"
        rounded_cost = item.get("rounded_total_cost")
        if rounded_cost is None:
            rounded_cost = utils.round_points(item.get("total_cost"))
        header_line = f"{name} × {item.get('count', 0)} (Koszt: {rounded_cost} pkt)"
        line_specs: list[tuple[str, float, int, str]] = [
            (PDF_BOLD_FONT, 11, 40, header_line)
        ]
        if item.get("custom_name"):
            base_line = f"Jednostka bazowa: {item.get('unit_name') or '-'}"
            line_specs.append((PDF_BASE_FONT, 10, 40, base_line))
        stats_line = (
            f"Jakość: {item.get('quality', '-')} | "
            f"Obrona: {item.get('defense', '-')} | "
            f"Wytrzymałość: {item.get('toughness', '-')}"
        )
        line_specs.append((PDF_BASE_FONT, 10, 40, stats_line))
        ability_sections: list[tuple[str, list[str]]] = []
        if item.get("passive_labels"):
            ability_sections.append(("Pasywne", item["passive_labels"]))
        if item.get("active_labels"):
            ability_sections.append(("Aktywne", item["active_labels"]))
        if item.get("aura_labels"):
            ability_sections.append(("Aury", item["aura_labels"]))

        if ability_sections:
            line_specs.append((PDF_BASE_FONT, 10, 40, "Zdolności:"))
            for label, values in ability_sections:
                base = f"{label}: {', '.join(values)}"
                for segment in wrap_line(base):
                    line_specs.append((PDF_BASE_FONT, 10, 50, segment))

        line_specs.append((PDF_BASE_FONT, 10, 40, "Uzbrojenie:"))

        for weapon in item.get("weapon_details", []):
            weapon_name = weapon.get("name") or "Broń"
            count = weapon.get("count") or 0
            range_value = weapon.get("range") or "-"
            attacks = weapon.get("attacks") or "-"
            ap_value = weapon.get("ap") if weapon.get("ap") is not None else "-"
            traits = weapon.get("traits") or "-"
            weapon_line = (
                f"- {weapon_name} × {count} | Z: {range_value} | "
                f"Ataki: {attacks} | AP: {ap_value} | Cechy: {traits}"
            )
            for segment in wrap_line(weapon_line):
                line_specs.append((PDF_BASE_FONT, 10, 50, segment))

        required_space = line_height * (len(line_specs) + 1)
        if y - required_space < margin:
            pdf.showPage()
            y = height - 50
            draw_page_header()

        for font_name, font_size, x_offset, text in line_specs:
            pdf.setFont(font_name, font_size)
            pdf.drawString(x_offset, y, text)
            y -= line_height
        y -= 6

    if spell_entries:
        required_space = line_height * (len(spell_entries) + 2)
        if y - required_space < margin:
            pdf.showPage()
            y = height - 50
            draw_page_header()
        pdf.setFont(PDF_BOLD_FONT, 12)
        pdf.drawString(margin, y, "Lista zaklęć")
        y -= 16
        pdf.setFont(PDF_BASE_FONT, 10)
        for spell in spell_entries:
            label = spell.get("label") or ""
            cost_text = spell.get("cost")
            prefix = f"{cost_text}: " if cost_text not in (None, "") else ""
            line = f"{prefix}{label}".strip()
            segments = wrap_line(line)
            for segment in segments:
                if y - line_height < margin:
                    pdf.showPage()
                    y = height - 50
                    draw_page_header()
                    pdf.setFont(PDF_BASE_FONT, 10)
                pdf.drawString(margin, y, segment)
                y -= line_height
        y -= 6

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    headers = {"Content-Disposition": f"attachment; filename=roster_{roster_id}.pdf"}
    return Response(buffer.getvalue(), media_type="application/pdf", headers=headers)
