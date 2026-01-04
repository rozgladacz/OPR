# OPR Army Builder

Serwerowa aplikacja FastAPI do budowania armii w systemie Moje OPR, modyfikacji One Page Rules. Projekt zawiera backend z szablonami Jinja2, podstawową autoryzacją sesyjną, przykładowymi danymi i mechanizmem kalkulacji kosztów jednostek.

## Konfiguracja

Aplikacja korzysta z pliku `.env` (ładowanego przez `python-dotenv`) w katalogu głównym repozytorium. Najważniejsze zmienne środowiskowe:

- `SECRET_KEY` – klucz używany przez `SessionMiddleware` do podpisywania ciasteczek; w środowisku produkcyjnym ustaw unikalną, długą wartość.
- `DB_URL` – adres bazy danych zgodny z SQLAlchemy, domyślnie `sqlite:///./data/opr.db`.
- `DEBUG` – flaga (np. `true`/`false`, `1`/`0`) włączająca tryb debugowania.

Przykład `.env`:

```
SECRET_KEY=zmien_to_na_bezpieczny_klucz
DB_URL=sqlite:///./data/opr.db
DEBUG=false
```

## Uruchomienie

1. Utwórz i aktywuj środowisko wirtualne:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. (Opcjonalnie) przygotuj plik `.env` z wartościami opisanymi w sekcji „Konfiguracja”.
3. Zainstaluj zależności:
   ```bash
   pip install -r requirements.txt
   ```
4. Zainicjuj bazę i uruchom aplikację (pierwszy start utworzy plik bazy oraz domyślne konto administratora `admin`/`admin`):
   ```bash
   uvicorn app.main:app --reload
   ```
   Aplikacja będzie dostępna pod adresem http://127.0.0.1:8000/.
5. Uruchomienie w trybie produkcyjnym (np. za reverse proxy):
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Backup i przywracanie bazy

Dostęp do narzędzi backupu mają wyłącznie administratorzy:

- W panelu admina (`/admin`) sekcja „Kopie zapasowe bazy danych” pozwala pobrać aktualny plik bazy (`Pobierz bazę danych`) lub wgrać kopię (`Wczytaj bazę danych`). Akcje te korzystają z endpointów `/users/backup` i `/users/restore`.
- Po wgraniu pliku aplikacja przywraca jego zawartość i przekierowuje z odpowiednim komunikatem.

## Dane przykładowe i testy

- Repozytorium zawiera przykładową bazę SQLite w `data/opr.db`, która może zostać zastąpiona podczas pierwszego uruchomienia lub przywracania.
- Scenariusze testowe rozpisek znajdują się w `tests/fixtures/rosters/`. Do uruchomienia testów wykorzystaj:
  ```bash
  pytest -q
  ```
