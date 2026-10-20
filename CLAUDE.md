# Mise — rules for agents

Restaurant ordering, kitchen display and revenue analytics. FastAPI + async SQLAlchemy 2.0 +
Alembic + Postgres 16 + Redis 7 (`services/api`), two Next.js 15 apps (`apps/guest-web`,
`apps/owner-web`), an OpenAI-compatible LLM adapter with a mock server
(`services/inference/mock`). Read `README.md`, `docs/architecture.md`, `docs/analytics.md`.

## Secrets
- Never read, print or commit `.env` or any API key. Do not run `cat .env`, `printenv`, `env`
  or `docker compose config`.
- Use `LLM_PROVIDER=mock` for every manual or integration check (shell variables override
  `.env` for Compose), e.g. `LLM_PROVIDER=mock DEMO_MODE=true make up`. Never call a real
  LLM provider.

## Policy
- Free-only: no paid APIs or paid defaults; keep the `:free` guard and the daily request cap.
- No sudo, apt, system installs or `docker system prune`. `make reset` is allowed (dev data
  is synthetic).
- Git: feature branches only; never commit to main, force-push, rewrite history or delete
  branches. Small commits, one logical change each.
- Never weaken, skip or xfail a test to make it pass. If a test is wrong, fix it and say why
  in the commit message.

## Architecture
- Async relationships are `lazy="raise"`; every query is explicit; never `db.refresh()` an
  object whose relationships are used afterwards.
- Every route has a `response_model`.
- Allergen status is deterministic server code; the model never decides it.
- The model never produces numbers: code computes them, the model only phrases them, and its
  text must pass the number-consistency check (`services/api/src/services/narrative.py`).
- Never send guest allergens, preferences, session ids or any personal data to a model. No
  client-supplied prompts.
- Cookies: `mise_auth` (owner and staff) and `mise_guest`. Languages: `en` and `it` only.
- No event or vendor-specific branding (`scripts/check_branding.sh`). README and docs
  describe only what is implemented and tested.

## Commands
- `make ci` — lint, all tests (Python in Docker, TS with Vitest), branding check.
- `make verify-f` — full Phase 1 verification against a fresh Docker stack.
