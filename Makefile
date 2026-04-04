
.PHONY: dev test

dev:
	python -m uvicorn app.main:app --reload

test:
<<<<<<< HEAD
	pytest -q


=======
	pytest -q
>>>>>>> Klasyfikacja
