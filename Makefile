
.PHONY: dev test test-fast lint smoke check safe-edit profile

# Force UTF-8 for every Python invocation in this Makefile.  Windows console
# defaults to cp1250 which crashes any script that prints arrows or Polish
# unit names (e.g. scripts/profile_quote.py).  See AGENTS.md "String Handling".
export PYTHONIOENCODING := utf-8

dev:
	python -m uvicorn app.main:app --reload

test:
	pytest -q

test-fast:
	pytest -q -x --tb=short

lint:
	python -m ruff check app/

check:
	make lint && make test-fast

safe-edit:
	@python -c "import sys, pathlib; [open(f,'r',encoding='utf-8').read() for f in sys.argv[1:] if pathlib.Path(f).exists()]" $(FILES)

smoke:
	@echo "=== Smoke test checklist (ręczny) ==="
	@echo "1. Zbrojownia       -> czy lista broni jest widoczna?"
	@echo "2. Edytor Armii     -> czy przy oddziale widoczne sa bronie?"
	@echo "3. Rozpiski         -> czy mozna zaznaczyc oddzial i otworzyc edytor?"
	@echo "Uruchom: make dev  i sprawdz powyzsze w przegladarce."

# Performance profiling for cost engine.  Usage:
#   make profile                # default ROSTER=10
#   make profile ROSTER=13      # any roster id
# Compare results with docs/PERFORMANCE.md baseline.
# PYTHONPATH=. so the script can `import app.*` when run from the repo root.
ROSTER ?= 10
profile:
	PYTHONPATH=. python scripts/profile_quote.py $(ROSTER)
