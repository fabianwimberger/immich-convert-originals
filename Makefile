.PHONY: all build up down clean lint

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
	@ruff check app/

format:
	@echo "Formatting code..."
	@ruff format app/
