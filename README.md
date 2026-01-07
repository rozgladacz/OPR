# OPR Army Builder

Serwerowa aplikacja FastAPI do budowania armii w systemie Moje OPR, modyfikacji One Page Rules. Projekt zawiera backend z szablonami Jinja2, podstawową autoryzacją sesyjną, przykładowymi danymi i mechanizmem kalkulacji kosztów jednostek.

## Konfiguracja

Aplikacja korzysta z pliku `.env` (ładowanego przez `python-dotenv`) w katalogu głównym repozytorium. Najważniejsze zmienne środowiskowe:

- `SECRET_KEY` – klucz używany przez `SessionMiddleware` do podpisywania ciasteczek; w środowisku produkcyjnym ustaw unikalną, długą wartość.
- `DB_URL` – adres bazy danych zgodny z SQLAlchemy, domyślnie `sqlite:///./data/opr.db`.
- `DEBUG` – flaga (np. `true`/`false`, `1`/`0`) włączająca tryb debugowania.
- `UPDATE_REPO_PATH` – ścieżka do repozytorium aktualizowanego przez panel admina; domyślnie `.`.
- `UPDATE_REF` – opcjonalny ref (gałąź/tag/commit), do którego ma zostać zresetowane repozytorium; gdy pusty, używana jest wartość z `UPDATE_BRANCH`.
- `UPDATE_DOCKERFILE` – ścieżka do Dockerfile używanego do budowy obrazu; domyślnie `Dockerfile`.
- `UPDATE_COMPOSE_FILE` – ścieżka do pliku docker-compose wykorzystywanego do odświeżenia kontenera; domyślnie `docker-compose.yml`.

Przykład `.env`:

```
SECRET_KEY=zmien_to_na_bezpieczny_klucz
DB_URL=sqlite:///./data/opr.db
DEBUG=false
UPDATE_REPO_PATH=.
UPDATE_REF=main
UPDATE_DOCKERFILE=Dockerfile
UPDATE_COMPOSE_FILE=docker-compose.yml
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

Domyślne konto administratora zostanie utworzone przy pierwszym uruchomieniu (`admin`/`admin`).

## Narzędzia developerskie

- Testy: `pytest -q` (lub `make test`)
- Uruchomienie serwera deweloperskiego: `uvicorn app.main:app --reload` (lub `make dev`)
