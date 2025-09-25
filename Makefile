
.PHONY: dev test seed

dev:
	uvicorn app.app:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

seed:
	python -m app.seed
