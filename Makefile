
.PHONY: dev test test-fast lint smoke

dev:
	python -m uvicorn app.main:app --reload

test:
	pytest -q

test-fast:
	pytest -q -x --tb=short

lint:
	python -m ruff check app/

smoke:
	@echo "=== Smoke test checklist (ręczny) ==="
	@echo "1. Zbrojownia       → czy lista broni jest widoczna?"
	@echo "2. Edytor Armii     → czy przy oddziale widoczne są bronie?"
	@echo "3. Rozpiski         → czy można zaznaczyć oddział i otworzyć edytor?"
	@echo "Uruchom: make dev  i sprawdź powyższe w przeglądarce."
