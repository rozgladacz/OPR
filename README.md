# OPR Army Builder

Serwerowa aplikacja FastAPI do budowania armii w systemie One Page Rules. Projekt zawiera backend z szablonami Jinja2, podstawową autoryzacją sesyjną, przykładowymi danymi i mechanizmem kalkulacji kosztów jednostek.

## Uruchomienie lokalne

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Aplikacja dostępna będzie pod adresem http://127.0.0.1:8000/.

Domyślne konto administratora zostanie utworzone przy pierwszym uruchomieniu (`admin`/`admin`).
