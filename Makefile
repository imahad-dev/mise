.PHONY: up down reset dev logs build migrate migration seed lint test test-py test-ts smoke gen-client setup ci verify-a

# --- Setup ---
setup:
	pnpm install --frozen-lockfile
	uv sync --project services/api

# --- Docker ---
up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

logs:
	docker compose logs -f

build:
	docker compose build

# --- Database ---
migrate:
	docker compose exec -T api alembic upgrade head

migration:
	docker compose exec -T api alembic revision --autogenerate -m "$(MSG)"

seed:
	docker compose exec -T api python scripts/seed.py

# --- Quality ---
lint:
	uv run --project services/api ruff check services/ scripts/
	uv run --project services/api ruff format --check services/ scripts/
	pnpm -r lint

test-py:
	docker compose build api-test && docker compose run --rm api-test

test-ts:
	pnpm -r test

test:
	$(MAKE) test-py
	$(MAKE) test-ts

verify-a:
	@bash scripts/verify_a.sh

# --- Inference ---
smoke:
	docker compose exec -T api python scripts/smoke_inference.py

# --- Client generation ---
gen-client:
	docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
	pnpm --filter api-client generate

# --- CI ---
ci:
	$(MAKE) setup
	$(MAKE) lint
	$(MAKE) test
