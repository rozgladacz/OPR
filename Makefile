
.PHONY: dev test

dev:
	python -m uvicorn app.main:app --reload

test:
	pytest -q


