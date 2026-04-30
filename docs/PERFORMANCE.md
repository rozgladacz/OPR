# Performance baseline — cost engine

Aktualizuj ten plik po każdej znaczącej zmianie w `app/services/costs.py`,
`app/routers/rosters.py:_internal_roster_unit_quote`, lub w eager-load options
(`_unit_eager_options`).  Reprodukcja:

```bash
make profile ROSTER=10        # full roster
make profile ROSTER=13        # alternatywny roster testowy
```

Wymagania:
- `data/opr.db` (produkcyjna baza — patrz AGENTS.md sekcja "Baza danych").
- `PYTHONIOENCODING=utf-8` (ustawione automatycznie przez Makefile).

---

## Aktualny baseline

**Data:** 2026-04-30
**Commit:** *(uzupełnij po commit'cie)*
**Roster:** 10 (10 oddziałów; mierzone `python scripts/profile_quote.py 10`)

| ru | Nazwa | wpns | abil | full(ms) | badge(ms) |
|---:|---|---:|---:|---:|---:|
| 70 | Leman Russ | 10 | 0 | 58.3 | 4.4 |
| 137 | Chmiera | 6 | 0 | 67.2 | 3.7 |
| 116 | Sentinel | 8 | 1 | 40.8 | 3.1 |
| 71 | Oficer | 4 | 2 | 21.5 | 1.5 |
| 72 | Piechota | 11 | 3 | 18.6 | 1.4 |
| 74 | Oficer szturmowy | 4 | 1 | 15.5 | 1.3 |
| 75 | Szturmowcy | 4 | 1 | 11.8 | 1.0 |
| 138 | Starszy Szczurak | 2 | 1 | 37.2 | 2.8 |
| 117 | Szczurak | 2 | 3 | 43.8 | 2.9 |
| 139 | Weterani | 9 | 1 | 19.8 | 1.1 |
| **TOTAL** | | | | **~334** | **~23** |

Cały zapis rostera (`/update`) z odświeżeniem badge'y mieści się w **<400 ms**
(backend) + opóźnienie sieci. Badge-only refresh per-oddział: ~1-4 ms.

> **Uwaga:** liczby są wrażliwe na konkretną zawartość rostera. Worst-case
> (Chmiera) ~67 ms wynika z liczby pasywek dynamicznych (transport).
> Przy regresji > 20% — uruchom `make profile` i porównaj sekcję cProfile.

---

## Historia (najnowsze na górze)

### 2026-04-30 — D1 + E2 + E3
- `@lru_cache` na `ability_identifier` i `normalize_name`.
- Hoist role-independent precompute z `_compute_total` do `roster_unit_role_totals`.
- Eliminacja O(N²) `next(...)` lookup w pętli ability.
- Memoizacja `_passive_entries` i `_ability_cost_map` po fingerprint cech.

**Mierzony wpływ (Leman Russ, `include_item_costs=True`):** 4480 ms → **41 ms** (≈110×).
**Worst-case po zmianie (Chmiera):** 55 ms.

### 2026-04-29 — Faza A1 + B1 + B2 (poprzednia runda)
- A1: usunięty duplikat `_internal_roster_unit_quote` w `_roster_unit_export_data` (~400-800 ms na eksport).
- B1: `scheduleRender()` z `requestAnimationFrame` w `app.js` (eliminuje burst-edit jank).
- B2: debounce quote 250 → 400 ms.

**Mierzony wpływ:** `/update` z ~30 s → ~3.5 s (przed dzisiejszą rundą).

---

## Hot paths — czego NIE dotykać bez pomiaru

Każdy z poniższych był diagnozowany przez `cProfile`. Komentarze w kodzie
opisują "co było, dlaczego problem, baseline w ms" — przed zmianą **przeczytaj komentarz**.

| Lokalizacja | Co | Dlaczego krytyczne |
|---|---|---|
| `costs.py:699` `ability_identifier` | `@lru_cache(4096)` | 18 700 wywołań/quote, czysta funkcja. Usunięcie cache = +200 ms/quote. |
| `costs.py:525` `normalize_name` | `@lru_cache(4096)` | Te same prawa, używane też przez ability_identifier. |
| `costs.py:~2126-2185` `roster_unit_role_totals` | Hoisted `_link_by_ability_id`, `_ability_id_to_ident`, `_base_active_set_precomputed` | Były role-independent, ale liczone 2× (warrior + strzelec). Cofnięcie hoist = O(N²) w `_compute_total`. |
| `costs.py:_passive_entries_cache` (closure) | Memoizacja po `tuple(sorted(traits))` | Warrior/strzelec różnią się jedną cechą — drugi wywołanie hituje cache. |
| `costs.py:1862` pętla `passive_deltas` | 2N × `roster_unit_role_totals` per quote | Świadomie pozostawione. Refactor = duże ryzyko. Rozważyć dopiero gdy worst-case > 200 ms. |
| `rosters.py:_internal_roster_unit_quote` | Adapter `RosterUnit -> Unit` dla `calculate_roster_unit_quote` | **Pułapka API:** `calculate_roster_unit_quote` przyjmuje `Unit`, nie `RosterUnit`. Przenieść do `costs.py` przy najbliższym refactorze. |
| `app.js:scheduleRender` (RAF) | Batchuje rendery edytora | Bez tego seria szybkich kliknięć `+/-` = N pełnych przebudów DOM. |
| `app.js` quote debounce 400 ms | `setTimeout` przy auto-save | Krótszy = więcej requestów na backend; dłuższy = laggy badge. |
| `_unit_eager_options` (`rosters.py:58`) | `selectinload(Weapon.parent).selectinload(Weapon.parent)` | **NIE jest duplikatem** — to grandparent loader (`utils.py:207-209`). |

---

## Konwencja `include_item_costs`

Dokumentowana w AGENTS.md (linia 135). Tu — kontekst kosztowy:

| Wartość | Co zwraca | Koszt | Kiedy |
|---|---|---|---|
| `True` | full breakdown z `passive_deltas` | ~10-60 ms / oddział | tylko aktywny edytowany oddział |
| `False` | sam `selected_total` (bez `item_costs`) | ~1-3 ms / oddział | wszystkie pozostałe badge refresh |

Naruszenie reguły (przekazanie `True` w pętli `refreshRosterCostBadges`)
przywróci poprzedni stan: ~14 s na zapis rostera 11-oddziałowego.

---

## Reguły utrzymania

1. **Każda optymalizacja w `costs.py` = komentarz `# Performance: <co było>, <baseline ms>`.**
   Bez tego następna sesja cofnie zmianę przy okazji "porządków".
2. **Po zmianie hot-pathu uruchom `make profile`** i zaktualizuj sekcję "Aktualny baseline".
3. **Regresja > 20%** — zatrzymaj się, zdiagnozuj cProfile, opisz w `HANDOFF.md`.
4. **Nowy `roster_unit_role_totals` caller** = oceń, czy potrzebuje
   `include_item_costs=True`. Domyślnie `False`.
