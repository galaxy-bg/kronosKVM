.PHONY: venv install-dev test lint check run

venv:
	python3 -m venv .venv

install-dev: venv
	.venv/bin/python -m pip install -e ".[dev]"

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

check: lint test

run:
	.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
