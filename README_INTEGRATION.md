
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

## Single source of truth for costs


### Migracja kontraktu endpointu quote (2026-03-29)

- Endpoint `POST /rosters/{roster_id}/units/{roster_unit_id}/quote` używa teraz parametru ścieżki `roster_unit_id` (wcześniej `unit_id`).
- W JSON odpowiedzi dodano pole `roster_unit_id` jako nowe pole docelowe.
- Pole `unit_id` jest zwracane tymczasowo dla kompatybilności wstecznej (deprecated) i powinno zostać usunięte po migracji klientów zewnętrznych.
- Jeśli integracja poza frontendem mapuje identyfikator jednostki z quote API, przełącz mapowanie na `roster_unit_id`.

### Kontrakt cache (`RosterUnit.cached_cost`)

- `cached_cost` jest **authoritative tylko po refreshu** wykonanym przez `app/services/costs.py::recalculate_roster_costs(...)`.
- `recalculate_roster_costs(roster, loadout_overrides=None)`:
  - przelicza wszystkie `roster_unit.cached_cost` w obrębie rozpiski,
  - zwraca krotkę `(roster_total, unit_cost_map)`, gdzie `unit_cost_map` to mapa `{roster_unit_id: koszt}`.
- `loadout_overrides` służy do tymczasowego przeliczenia (np. przy edycji formularza), ale wynik nadal jest zapisywany do `cached_cost`.

### Zasada architektoniczna: brak wielowątkowości na ORM Session i żywych encjach

- **Nie uruchamiamy workerów równoległych** na obiektach SQLAlchemy (`Session`, encje ORM, relacje lazy/eager).
- Operacje `quote` / `update` wykonują się per-request z własną sesją i bez współdzielenia sesji między wątkami.
- Zapis `cached_cost` pozostaje **sekwencyjny** w granicach jednego requestu i jednej transakcji.

### Snapshot przed ewentualną równoległością CPU

Jeśli pojawi się potrzeba równoległych obliczeń CPU:

1. Najpierw wykonujemy etap **snapshotu**: serializacja danych wejściowych do niemutowalnych DTO/dict/list/tuple (bez referencji do ORM).
2. Dopiero potem uruchamiamy worker pool wyłącznie na tych snapshotach.
3. Wyniki z workerów składamy ponownie w wątku requestu i dopiero wtedy wykonujemy sekwencyjny zapis `cached_cost` w aktywnej sesji.

Ten schemat eliminuje ryzyko współdzielenia sesji między wątkami i race condition na żywych encjach.

### Kiedy `cached_cost` musi być invalidated

Traktuj `cached_cost` jako przeterminowany po każdej zmianie wpływającej na koszt, m.in.:
- zmiana `count` jednostki,
- zmiana `extra_weapons_json` / loadoutu (broń, pasywki, aktywki, aury),
- zmiana klasyfikacji roli (`wojownik`/`strzelec`) wynikającej z loadoutu,
- zmiany danych bazowych jednostki/zdolności/broni (po stronie danych źródłowych).

W praktyce zamiast „ręcznego” unieważniania pojedynczych pól, stosujemy pełny refresh przez
`recalculate_roster_costs(...)` dla całej rozpiski przed odpowiedzią.

### Endpointy z obowiązkowym refresh przed odpowiedzią

- Widok edycji rozpiski: `GET /rosters/{roster_id}`.
- Operacje zwracające JSON z aktualnym `total_cost` po zmianie jednostki:
  - `POST /rosters/{roster_id}/units/add` (ścieżka JSON),
  - `POST /rosters/{roster_id}/units/{roster_unit_id}/update-loadout` (ścieżka JSON).
- Eksporty:
  - `GET /rosters/{roster_id}/print`,
  - `GET /rosters/{roster_id}/export/lista`,
  - `GET /rosters/{roster_id}/pdf`,
  - `GET /export/xlsx/{roster_id}`.

W tych miejscach `roster_total` ma pochodzić z `recalculate_roster_costs(...)`, nie z ręcznego sumowania.
