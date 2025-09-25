
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
try:
    from openpyxl import Workbook
except Exception as e:
    Workbook = None

# Import your ORM session and models here as in other routers
try:
    from app.db import get_session  # adjust to your project
except Exception:
    get_session = None

router = APIRouter(prefix="/export", tags=["export"])  # register in app

def _append_roster_sheets(wb, roster):
    ws = wb.active
    ws.title = "Lista"
    ws.append(["Jednostka","#","Jakość","Obrona","Wytrzymałość","Zdolności","Broń","Koszt modeli","Koszt broni","Koszt zdolności","Suma"])
    total_sum = 0
    for item in getattr(roster, "items", []):
        u = getattr(item, "unit", None) or getattr(item, "template_unit", None)
        name = getattr(u, "name", "UNIT")
        q = getattr(u, "quality", "-")
        d = getattr(u, "defense", "-")
        t = getattr(u, "tough", getattr(u, "toughness", "-"))
        abil_list = getattr(u, "abilities", []) or []
        abil_txt = ", ".join(getattr(a,"name", str(a)) for a in abil_list)
        # weapons (best-effort)
        wpn_list = getattr(u, "weapons", []) or []
        wpn_txt = ", ".join(getattr(w,"name", str(w)) for w in wpn_list)
        models = getattr(item, "models", 1)
        km = int(getattr(item, "cost_models", 0))
        kw = int(getattr(item, "cost_weapons", 0))
        ka = int(getattr(item, "cost_abilities", 0))
        total = int(getattr(item, "total_cost", km+kw+ka))
        ws.append([name, models, q, d, t, abil_txt, wpn_txt, km, kw, ka, total])
        total_sum += total
    # Summary row
    ws.append(["", "", "", "", "", "", "SUMA", "", "", "", total_sum])
    # Used Armory sheet
    ws2 = wb.create_sheet("Zbrojownia użyta")
    ws2.append(["Nazwa","Zasięg","Ataki","AP","Cechy"])
    used = {}
    for item in getattr(roster, "items", []):
        u = getattr(item, "unit", None) or getattr(item, "template_unit", None)
        for w in getattr(u, "weapons", []) or []:
            key = getattr(w, "name", str(w))
            if key in used: 
                continue
            rng = getattr(w, "range", getattr(w, "rng", "-"))
            atk = getattr(w, "attacks", getattr(w, "atk", "-"))
            ap  = getattr(w, "ap", "-")
            traits = getattr(w, "traits", []) or []
            traits_txt = ", ".join(getattr(t,"name", str(t)) for t in traits) if isinstance(traits, (list, tuple)) else str(traits)
            used[key] = (rng, atk, ap, traits_txt)
    for name, (rng, atk, ap, traits_txt) in used.items():
        ws2.append([name, rng, atk, ap, traits_txt])

@router.get("/xlsx/{roster_id}")
def export_xlsx(roster_id: int):
    if Workbook is None:
        raise HTTPException(status_code=500, detail="Brak biblioteki openpyxl – dodaj do requirements.txt: openpyxl")
    # Load roster by ID with eager relations; adapt to your project conventions.
    roster = None
    try:
        # Pseudo-code: replace with actual session/ORM code as in your project
        # with get_session() as s: roster = s.get(Roster, roster_id)
        pass
    except Exception:
        roster = None
    if roster is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono rozpiski")
    wb = Workbook()
    _append_roster_sheets(wb, roster)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=roster_{roster_id}.xlsx"})
