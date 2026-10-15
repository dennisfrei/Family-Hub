# Settings and defaults come from .env (copy of .env.example)
-include .env

IMAGE_NAME ?= family-hub
IMAGE = $(if $(REGISTRY),$(REGISTRY)/,)$(IMAGE_NAME)
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
PLATFORM ?=
PYTHON_PATHS = src alembic

.DEFAULT_GOAL := help
.PHONY: help install db s3 services down run lint lint-check format format-check typecheck test test-integration test-all \
	check migrate migrate-new token backup backup-s3 restore restore-s3 restore-list build push release

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Development -----------------------------------------------------------

install: ## Install dependencies incl. dev tools
	uv sync

db: ## Start PostgreSQL (docker compose)
	docker compose up -d --wait db

s3: ## Start the local S3 (RustFS) for backup tests
	docker compose up -d s3

services: db s3 ## Start PostgreSQL and S3

down: ## Stop all compose services
	docker compose down

run: db ## Run the app on http://localhost:8080 (migrates on start)
	uv run family-hub

# --- Quality ---------------------------------------------------------------

lint: ## Lint and fix
	uvx ruff check $(PYTHON_PATHS) --fix

format: ## Format code
	uvx ruff format $(PYTHON_PATHS)

format-check: ## Check formatting without changing files
	uvx ruff format --check $(PYTHON_PATHS)

typecheck: ## Type check with ty
	uv run ty check $(PYTHON_PATHS)

test: ## Unit tests (no database needed)
	uv run pytest -m "not integration"

test-integration: db ## Integration tests against PostgreSQL (database <name>_test)
	uv run pytest -m integration

test-all: db ## All tests
	uv run pytest

lint-check: ## Lint without changing files
	uvx ruff check $(PYTHON_PATHS)

check: lint-check format-check typecheck test-all ## Everything CI checks: lint, format, types, all tests

# --- Database and data -----------------------------------------------------

migrate: ## Apply migrations
	uv run alembic upgrade head

migrate-new: ## New migration (MSG="...")
	@test -n "$(MSG)" || (echo 'Usage: make migrate-new MSG="add something"' && exit 1)
	uv run alembic revision --autogenerate -m "$(MSG)"

token: ## Issue an API token (NAME=client, DAYS=365)
	@test -n "$(NAME)" || (echo "Usage: make token NAME=ios-shortcut [DAYS=365]" && exit 1)
	uv run family-hub-token $(NAME) --days $(or $(DAYS),365)

backup: ## Local backup to ./backups
	uv run family-hub-backup

backup-s3: ## Backup to S3, skipped when unchanged
	uv run family-hub-backup --s3

restore: ## Restore a local file (FILE=...)
	@test -n "$(FILE)" || (echo "Usage: make restore FILE=backups/<file>.json.gz" && exit 1)
	uv run family-hub-restore $(FILE)

restore-s3: ## Restore from S3 (KEY=...)
	@test -n "$(KEY)" || (echo "Usage: make restore-s3 KEY=<prefix>/<file>.json.gz" && exit 1)
	uv run family-hub-restore --s3 --key $(KEY)

restore-list: ## List backups in S3
	uv run family-hub-restore --list

# --- Image -----------------------------------------------------------------

build: ## Build the image as IMAGE:TAG and IMAGE:latest (TAG defaults to the git sha, PLATFORM optional)
	docker build $(if $(PLATFORM),--platform $(PLATFORM)) -t $(IMAGE):$(TAG) -t $(IMAGE):latest .
	@docker image ls $(IMAGE):$(TAG) --format "Built {{.Repository}}:{{.Tag}} ({{.Size}})"

push: ## Push IMAGE:TAG and IMAGE:latest (needs REGISTRY)
	@test -n "$(REGISTRY)" || (echo "Set REGISTRY in .env or on the command line" && exit 1)
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

release: check build push ## Check, build and push
