# HANDOFF

> Plik prowadzony zgodnie z AGENTS.md (linia 57). Aktualizuj po każdym
> znaczącym kroku. Po zakończeniu wątku — zostaw stan końcowy lub wyczyść
> sekcje "W toku" / "Hipotezy".

## Aktualny cel
*(jedno zdanie — co próbujemy osiągnąć w bieżącej sesji)*

—

## Pliki dotknięte w bieżącej sesji
*(ścieżka — krótki opis zmiany)*

—

## Hipotezy / pytania otwarte
*(co zakładamy, czego jeszcze nie zweryfikowaliśmy)*

—

## W toku
*(kroki rozpoczęte ale niedokończone — z numerami linii / nazwami funkcji)*

—

## Jak zweryfikować
*(konkretne komendy / scenariusze do odpalenia po wznowieniu)*

—

---

## Log sesji (dopisuj na górze)

### 2026-04-30 — Optymalizacja cost engine (D1+E2+E3)

**Cel:** Sprowadzić `calculate_roster_unit_quote(include_item_costs=True)`
na dużych oddziałach (Chimera/Leman Russ na rosters/10) z kilkunastu sekund
do <100 ms.

**Zmiany:**
- `app/services/costs.py:525` — `@lru_cache(maxsize=4096)` na `normalize_name`.
- `app/services/costs.py:699` — `@lru_cache(maxsize=4096)` na `ability_identifier`
  (~18 700 wywołań/quote → cache hit ratio ~99.5%).
- `app/services/costs.py:2061-2185` — w `roster_unit_role_totals`:
  - hoist `_sorted_ability_links`, `_link_by_ability_id`, `_ability_id_to_ident`,
    `_base_active_set_precomputed`, `_selected_active_set_precomputed` poza
    `_compute_total` (były role-independent, ale liczone 2× na każdy quote).
  - eliminacja O(N²) `next(...)` lookup w pętli ability (linie 2168-2176 sprzed zmiany).
  - memoizacja `_passive_entries` i `_ability_cost_map` po fingerprint cech
    (warrior i strzelec różnią się jedną cechą → cache hit na drugim wywołaniu).
- `app/services/costs.py:2270` — `ability_identifier(slug)` w pętli passive_diff
  było wywoływane 2× na entry, teraz 1×.

**Baseline (przed → po) na rosters/10:**
| Oddział | Przed | Po |
|---|---|---|
| Leman Russ | 4480 ms | **41 ms** |
| Chmiera | ~kilkanaście s (raport użytkownika) | **55 ms** |
| Pozostałe | — | 9–36 ms |

Cały roster ~14 s → ~300 ms (≈50× szybciej). Badge-only refresh: 3 ms/oddział.

**Weryfikacja:**
- `pytest tests/ -q` → 140/140 passed.
- `make profile ROSTER=10` (po wprowadzeniu w 6.2) — patrz `docs/PERFORMANCE.md`.

**Pominięte świadomie:**
- E1 (refactor pętli `passive_deltas` w `calculate_roster_unit_quote:1860-1873`)
  — nieuzasadnione przy obecnych <100 ms na worst-case.
- D2/D3 (memoizacja `weapon_cost_components` / `ability_cost_components_from_name`)
  — pozostają hot, ale ich łączny koszt jest <50 ms na cały roster.

**Wcześniejsze fazy ukończone (ten i poprzedni dzień):**
- A1 — usunięty duplikat quote w `_roster_unit_export_data` (rosters.py).
- B1 — `scheduleRender()` z RAF batching (app.js).
- B2 — debounce quote 250 → 400 ms (app.js).

**Pominięte i odłożone:**
- A2 — `selectinload(Weapon.parent).selectinload(Weapon.parent)` w `_unit_eager_options`
  okazał się intencjonalnym dziadkiem (`utils.py:207-209`), nie duplikatem.
- B3 — skip render gdy zmienia się tylko `count`. Niepotrzebne po B1.
- C1 — lazy unit_payloads + AJAX endpoint. Osobne zadanie, niższy priorytet.
