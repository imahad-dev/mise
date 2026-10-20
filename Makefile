.PHONY: up down reset dev logs build migrate migration seed simulate lint test test-py test-ts e2e smoke smoke-llm gen-client setup ci verify-a verify-b verify-c verify-d verify-e verify-f

# --- Setup ---
setup:
	pnpm install --frozen-lockfile
	uv sync --project services/api

# --- Docker ---
up:
	docker compose up -d --build --wait

down:
	docker compose --profile edge --profile test down

reset:
	docker compose --profile edge --profile test down -v

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

simulate:
	docker compose exec -T api python scripts/simulate.py

# --- Quality ---
lint:
	uv run --project services/api ruff check services/ scripts/
	uv run --project services/api ruff format --check services/ scripts/
	pnpm -r lint

test-py:
	docker compose build api-test && docker compose run --rm api-test

test-ts:
	pnpm -r test

# Browser tests against a running stack (LLM_PROVIDER=mock DEMO_MODE=true make up)
e2e:
	pnpm exec playwright test

test:
	$(MAKE) test-py
	$(MAKE) test-ts

verify-a:
	@bash scripts/verify_a.sh

verify-b:
	@bash scripts/verify_b.sh

verify-c:
	@bash scripts/verify_c.sh

verify-d:
	@bash scripts/verify_d.sh

verify-e:
	@bash scripts/verify_e.sh

verify-f:
	@bash scripts/verify_phase1.sh

# --- Inference ---
smoke:
	docker compose exec -T api python scripts/smoke_inference.py

smoke-llm:
	docker compose exec -T api python scripts/smoke_llm.py

# --- Client generation ---
gen-client:
	docker compose exec -T api python scripts/export_openapi.py > packages/api-client/openapi.json
	pnpm --filter api-client generate

# --- CI ---
ci:
	$(MAKE) setup
	$(MAKE) lint
	$(MAKE) test
	@bash scripts/check_branding.sh
