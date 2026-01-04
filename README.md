# OPR Army Builder

Serwerowa aplikacja FastAPI do budowania armii w systemie Moje OPR, modyfikacji One Page Rules. Projekt zawiera backend z szablonami Jinja2, podstawową autoryzacją sesyjną, przykładowymi danymi i mechanizmem kalkulacji kosztów jednostek.

## Uruchomienie lokalne

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # podstawowe zależności aplikacji
# lub: pip install -r requirements-dev.txt  # zależności podstawowe + testy/dev
uvicorn app.main:app --reload
```

Aplikacja dostępna będzie pod adresem http://127.0.0.1:8000/.

Domyślne konto administratora zostanie utworzone przy pierwszym uruchomieniu (`admin`/`admin`).

## Narzędzia developerskie

- Testy: `pytest -q` (lub `make test`)
- Uruchomienie serwera deweloperskiego: `uvicorn app.main:app --reload` (lub `make dev`)
