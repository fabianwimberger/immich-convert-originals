.PHONY: all build up down clean lint format typecheck test integration

PYTHON ?= .venv/bin/python

all: build

build:
	@echo "Building Docker images..."
	@docker compose build

up:
	@echo "Starting service..."
	@docker compose up

down:
	@echo "Stopping service..."
	@docker compose down

clean:
	@echo "Cleaning up..."
	@docker compose down -v

lint:
	@echo "Running linters..."
	@$(PYTHON) -m ruff check backend/

format:
	@echo "Formatting code..."
	@$(PYTHON) -m ruff format backend/

typecheck:
	@echo "Running type checker..."
	@$(PYTHON) -m mypy backend/app

test:
	@echo "Running unit tests..."
	@$(PYTHON) -m pytest -m "not integration" -v --cov-fail-under=85

integration:
	@echo "Running integration tests..."
	@$(PYTHON) -m pytest -m integration -v
