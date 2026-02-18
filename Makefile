.PHONY: install lint format test test-cov build run clean

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

test:
	pytest

test-cov:
	pytest --cov=cal_ai --cov-report=term-missing --cov-report=html

build:
	docker compose build

run:
	docker compose up

clean:
	rm -rf .ruff_cache .pytest_cache htmlcov .coverage
	rm -rf src/*.egg-info dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
