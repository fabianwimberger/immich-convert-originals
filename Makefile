.PHONY: all build up down clean lint test integration

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
	@ruff check backend/

format:
	@echo "Formatting code..."
	@ruff format backend/

test:
	@echo "Running unit tests..."
	@pytest -m "not integration" -v

integration:
	@echo "Running integration tests..."
	@pytest -m integration -v
