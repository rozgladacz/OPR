# AGENTS.md

## Cel projektu
Aplikacja służy do przygotowywania list (Rozpisek) do gry.

Główne obszary:
- Rozpiski
- Armie
- Zbrojownie

Zależności:
- Rozpiski są budowane na podstawie Armii.
- Armie są budowane na podstawie Zbrojowni.
- Zasady gry znajdują się w `app/static/docs` i są źródłem prawdy.

## Model danych i dziedziczenie
- Armie i Rozpiski muszą wspierać hierarchię i dziedziczenie.
- Wariant ma przechowywać tylko różnice względem bazy.
- Nie duplikuj pełnego stanu, jeśli wystarczą nadpisania.
- Zachowuj stabilne identyfikatory obiektów, jeśli już istnieją.
- Zmiana modelu danych musi uwzględniać wpływ na warianty potomne.

## Baza danych
- Traktuj bazę jako środowisko testowe, ale współdzielone.
- Nie wykonuj destrukcyjnych operacji bez wyraźnego polecenia. Zawsze trzymaj kopię zapasową.
- Jeśli zadanie wymaga migracji lub zmian danych, opisz ich wpływ i przygotuj proces migracji.
- Przed zakończeniem prac i udostępnieniem Preview do akceptacji podłącz bazę z danymi produkcyjnymi (`data/opr.db`). Preview z pustą bazą nie nadaje się do weryfikacji przez użytkownika.
- Zawsze trzymaj kopię oryginalnej bazy (`data/opr.db.backup` lub commit w git), aby móc ją przywrócić po testach. Wersja w git jest źródłem prawdy — przywracaj przez `git show <commit>:data/opr.db > data/opr.db`.

## Użytkownicy i uprawnienia
- System ma mieć dwa poziomy dostępu:
  - `admin`
  - `user`
- Funkcje administracyjne muszą być jawnie odseparowane od zwykłego użytkownika.
- Nie rozszerzaj uprawnień użytkownika bez wyraźnego wymagania.

## Dokumentacja reguł
- Pliki w `app/static/docs` są tylko do odczytu.
- Nie modyfikuj ich bez osobnego zadania.
- Jeśli kod i dokumentacja są sprzeczne, zatrzymaj się i opisz rozbieżność.
- Nie zgaduj znaczenia reguły, jeśli nie wynika ono jasno z dokumentu lub kodu.

## Zasady pracy
- Najpierw czytaj istniejący kod, potem edytuj.
- Dla zadań wieloetapowych najpierw przygotuj krótki plan.
- Dla zadań prostych wykonuj minimalny lokalny patch.
- Nie przebudowuj architektury bez potrzeby.
- Preferuj małe, odwracalne zmiany.

## Testy i weryfikacja
- Po zmianie logiki uruchom testy związane z dotkniętym obszarem.
- Po zmianie UI sprawdź też stan pusty, błędny i podstawowy scenariusz.
- Jeśli testów brakuje, dodaj minimalny test regresji.
- Nie uznawaj zadania za zakończone bez krótkiej weryfikacji diffu.
- Na początku analizy wymagań oceń, czy zlecone zadanie dezaktualizuje istniejące testy. Jeśli tak — popraw lub usuń je jako pierwszy krok, zanim zmienisz kod produkcyjny. Nieaktualne testy blokują pracę i generują fałszywe błędy.

## Konwencje zmian
- Nie zmieniaj formatowania poza zakresem zadania.
- Nie wprowadzaj dodatkowych refaktorów przy okazji małej zmiany.
- Jeśli poprawiasz błąd, opisz przyczynę i zakres poprawki.
- Jeśli zmieniasz model dziedziczenia, sprawdź zgodność z edycją wariantów potomnych.
- **Duże usunięcia z monolitycznych plików (app.js, rosters.py, armies.py):** podziel na osobne commity per kategoria (np. stałe, funkcje kosztowe, helpery UI). Jeden commit nie powinien usuwać więcej niż ~150 linii z jednego pliku bez weryfikacji każdej usuwanej funkcji przez `grep`.

## Komentarze sekcji
Pliki `app/static/js/app.js`, `app/services/costs.py`, `app/routers/rosters.py` mają komentarze sekcji w formacie:
- JS: `// === SECTION: Nazwa — opis ===`
- Python: `# === SECTION: Nazwa — opis ===`

**Zasady utrzymania:**
- Analizując plik — przeczytaj komentarze sekcji jako mapę, zanim zaczniesz przeszukiwać kod.
- Dodając nową funkcję — umieść ją w odpowiedniej sekcji; jeśli nie pasuje do żadnej, dodaj nowy nagłówek sekcji.
- Przenosząc lub usuwając funkcję wymienioną w nagłówku sekcji — zaktualizuj listę funkcji w komentarzu.
- Tworząc nowy plik z logiką (>100 linii) — dodaj komentarze sekcji od razu.
- Nie dodawaj komentarzy do krótkich plików pomocniczych (<50 linii) ani do szablonów HTML.

## Smoke test po zmianie app.js
Po każdej zmianie `app/static/js/app.js` uruchom aplikację (`make dev`) i ręcznie sprawdź:
1. **Zbrojownia** → czy lista broni jest widoczna?
2. **Edytor Armii** → czy przy dodaniu oddziału widoczne są bronie?
3. **Rozpiski** → czy można zaznaczyć oddział i czy otwiera się panel edytora?

Testy backendowe (`make test`) nie pokrywają inicjalizacji JS — te trzy scenariusze muszą być sprawdzone ręcznie.

## Struktura app.js
`app/static/js/app.js` to monolityczny plik (~6500 linii). Plik zawiera komentarze sekcji oznaczone `// === SECTION: ... ===`. Struktura:

```
GLOBAL STATE & REFRESH TOKEN UTILS  (linia ~1)
ABILITY PICKER                       (linia ~50)
TEXT PARSING UTILS                   (linia ~689)
SPELL WEAPON COST PREVIEW            (linia ~842)
UI PICKERS — NUMBER, RANGE           (linia ~976)   ← KRYTYCZNE: helpery UI, NIE silnik kosztów
WEAPON PICKER                        (linia ~1292)
ROSTER ITEM RENDERING                (linia ~2314)
LOADOUT STATE MANAGEMENT             (linia ~2664)
EDITOR RENDERERS                     (linia ~3072)
ROSTER ADDERS                        (linia ~3488)
ROSTER EDITOR CLOSURE                (linia ~3590)   ← domknięcie ~2000 linii
SPELL ABILITY FORMS                  (linia ~5849)
ARMORY WEAPON TREE                   (linia ~6039)
BOOTSTRAP — DOMContentLoaded         (linia ~6544)
```

**Łańcuch inicjalizacji DOMContentLoaded (kolejność krytyczna):**
```
initAbilityPickers → initNumberPickers → initRangePickers →
initWeaponPickers → initRosterEditor → initWeaponDefaults →
initSpellAbilityForms → initArmoryWeaponTree → initSpellWeaponCostPreview
```
Funkcje `initNumberPicker(s)`, `initRangePicker(s)`, `initWeaponDefaults` to **helpery UI** (spinners liczb, zakresy broni) — **nie są częścią silnika kosztów**. Ich usunięcie niszczy całą inicjalizację przez ReferenceError.

**Reguła bezpieczeństwa dla dużych plików:** przed usunięciem dowolnej funkcji z `app.js` uruchom:
```bash
grep -n "nazwaFunkcji" app/static/js/app.js
```
i zweryfikuj brak wywołań. W szczególności sprawdź łańcuch DOMContentLoaded.

**Domknięcie `initRosterEditor`** (linia ~3590–5848): zawiera ~60 prywatnych funkcji współdzielących stan przez closure-scope (`loadoutState`, `activeItem`, `refreshRosterCostBadgesInProgress`, itp.). Zmiana jednej funkcji może mieć efekty uboczne w innych przez wspólne zmienne.

**Konwencja `include_item_costs`:** badge-only calls do `/quote` zawsze przekazują `include_item_costs: false`. Tylko dedykowany quote aktywnego oddziału w `handleStateChange` przekazuje `true`. Naruszenie tej reguły przywróci wielokrotnie wolniejsze badge refresh.

## Komendy projektu
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
- Run: `make dev`
- Test (wszystkie): `make test`
- Test (szybki, stop na pierwszym błędzie): `make test-fast`
- Lint: `make lint`

## Oczekiwany sposób pracy agenta
- Przed zmianą wskaż pliki, które zamierzasz edytować.
- Odczytuj pliki batchami
- Jeśli wymaganie jest niejasne, najpierw wypisz założenia i braki.
- Po wykonaniu zmian podaj:
  - co zmieniono
  - jak zweryfikowano
  - co nadal wymaga decyzji
