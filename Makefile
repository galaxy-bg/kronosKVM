.PHONY: venv install-dev test lint check run container-build container-up container-down

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

container-build:
	docker-compose -f compose.yaml build

container-up:
	docker-compose -f compose.yaml up -d

container-down:
	docker-compose -f compose.yaml down
