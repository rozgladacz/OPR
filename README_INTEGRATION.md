
# OPR Patch: Rozpiski – ostrzeżenia, eksport XLSX, styl 'lista', ruleset JSON, test fixtures

Ten pakiet dodaje:
- `app/services/rules.py` – zbieranie **ostrzeżeń** (miękkie walidacje) dla rozpiski.
- `app/routers/export_xlsx.py` – endpoint eksportu **XLSX** dla rozpiski.
- `app/templates/export/lista.html` – alternatywny styl eksportu **'lista'** (HTML/PDF).
- `app/rulesets/default.json` – domyślny **RuleSet** w JSON.
- `tests/fixtures/rosters/*.yaml` + `tests/test_rosters_from_fixtures.py` – **scenariusze testowe** (bez Excela).

## Integracja (dla Codex / lub ręcznie)

1. **Zarejestruj router exportu XLSX** w aplikacji (np. w `app.py`/`main.py`):
   ```python
   from app.routers import export_xlsx
   app.include_router(export_xlsx.router)
   ```
   Upewnij się, że w `requirements.txt` jest `openpyxl`.

2. **Ostrzeżenia w rozpisce** – w `routers/rosters.py` po zbudowaniu obiektu `roster` dodaj:
   ```python
   from app.services.rules import collect_roster_warnings
   warnings = collect_roster_warnings(roster)
   context["warnings"] = warnings
   ```
   W `templates/roster_edit.html` (lub analogicznym) wstaw panel:
   ```jinja2
   {% if warnings %}
     <div class="alert alert-warning">
       <strong>Ostrzeżenia:</strong>
       <ul>{% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>
     </div>
   {% else %}
     <div class="alert alert-success">Brak ostrzeżeń.</div>
   {% endif %}
   ```

3. **Eksport HTML 'lista'** – dodaj link/akcję do renderu `templates/export/lista.html`
   (np. w istniejącym routerze eksportu HTML/PDF):
   ```python
   return templates.TemplateResponse("export/lista.html", {"request": request, "roster": roster})
   ```

4. **RuleSet (opcjonalnie)** – jeśli masz model RuleSet:
   - Umieść `app/rulesets/default.json` i doładuj jako domyślne parametry (fallback).
   - W kalkulatorze kosztów odczytuj wartości z aktywnego RuleSet.

5. **Testy/CI** – `pytest -q`. Pliki w `tests/fixtures/rosters/` są gotowe
   do rozbudowy – dodawaj kolejne przypadki, aby odwzorować „list z Excela”.

> Pakiet nie nadpisuje istniejących plików. Wszystkie zmiany są **dodatkowe** i bezpieczne.
