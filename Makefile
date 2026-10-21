.PHONY: install test run migrate lint check

install:
	python -m pip install -r requirements-dev.txt

test:
	python -m pytest -q

run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

migrate:
	alembic upgrade head

lint:
	ruff check app tests scripts validation_core.py

check: lint test
