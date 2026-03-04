.PHONY: install lint format test test-cov test-regression test-regression-live test-memory test-memory-live benchmark build run clean clean-memory serve serve-dev

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

test-regression:
	pytest tests/regression/ -v

test-regression-live:
	pytest tests/regression/ --live -v -n 5

test-memory:
	pytest tests/regression/test_memory_roundtrip.py -v

test-memory-live:
	pytest tests/regression/test_memory_roundtrip.py --live -v

benchmark:
	python -m cal_ai benchmark

build:
	docker compose build

run:
	docker compose up

clean:
	rm -rf .ruff_cache .pytest_cache htmlcov .coverage
	rm -rf src/*.egg-info dist build
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-memory:
	rm -f data/memory*.db data/memory*.db-wal data/memory*.db-shm

serve:
	python -m cal_ai serve

serve-dev:
	python -m cal_ai serve -v
