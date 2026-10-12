# Mise — Revenue Copilot for Independent Restaurants

> AMD Developer Hackathon: ACT III, Track 3 — Reinvent Commerce

Mise is a revenue copilot for independent restaurants. Guests scan a table QR code and order from a mobile web page in their preferred language. Every order feeds a demand forecast and margin model. Each morning, owners get an action brief (what to prep, pull, promote, or reprice) and approve actions with one tap to update the live menu.

All AI models run on AMD ROCm GPUs served with vLLM (with a local OpenAI-compatible mock server for fast local development and CI).

---

## Architecture Overview

```
                      ┌──────────────────────┐
                      │   Reverse Proxy /    │
                      │  Next.js Rewrites    │
                      └──────┬────────┬──────┘
                             │        │
               ┌─────────────┘        └─────────────┐
               ▼                                    ▼
       apps/guest-web (3000)                apps/owner-web (3001)
         (Guest UI & Ordering)             (Kitchen & Owner Dashboard)
               │                                    │
               └─────────────┬──────────────────────┘
                             ▼
                    services/api (8000)
                     FastAPI + SQLAlchemy
                      (AsyncPG / Psycopg)
                        │           │
            ┌───────────┴───┐   ┌───┴──────────┐
            ▼               ▼   ▼              ▼
     Postgres 16          Redis 7      services/inference (8080)
    (Relational DB)    (Pub/Sub, Cache)  (vLLM / ROCm or Mock)
```

### Key Highlights
- **Single-Origin Architecture**: Next.js route rewrites proxy allowed `/api/*` endpoints to FastAPI. No CORS setup, zero build-time API URLs.
- **Role-Separated Auth**: Three distinct signed httpOnly cookies (`mise_guest` with SameSite=Lax, `mise_owner`, `mise_staff`).
- **Allergen Safety Engine**: Server-authoritative matching strictly adhering to the EU-14 allergen list with precedence `contains > unverified > no_declared_match`. Snapshots allergen states on each `order_item` at placement.
- **Real-Time Streaming**: Server-Sent Events (SSE) for order updates and kitchen tickets with 15-second heartbeats and reconnection handling.
- **Hardware-Efficient Inference**: OpenAI-compatible client tracking token usage and latencies directly into `metrics_sample`.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 22 LTS & pnpm 9 (`corepack enable`)
- Python 3.11 & uv (`astral-sh/uv`)

### 1. Environment Setup

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

> **Note on Security**: In production (`APP_ENV=production`), the API refuses to boot if default secret keys (`API_SECRET_KEY`, `OWNER_API_KEY`, `STAFF_PIN`) are left unchanged.

### 2. Boot Services with Docker Compose

```bash
# Start all containers in background
docker compose up -d

# Check service health
docker compose ps
```

Health checks ping:
- Postgres (`5432`): `pg_isready -h 127.0.0.1 -U mise`
- Redis (`6379`): `redis-cli -h 127.0.0.1 ping`
- API (`8000`): `http://127.0.0.1:8000/health`
- Mock Inference (`8080`): `http://127.0.0.1:8080/v1/models`
- Guest Web (`3000`): `http://127.0.0.1:3000/`
- Owner Web (`3001`): `http://127.0.0.1:3001/`

### 3. Verify Health & Inference

```bash
# Verify health endpoint
curl http://localhost:8000/health

# Run inference smoke test
docker compose exec -T api python scripts/smoke_inference.py
```

### 4. Running Tests & Linting

```bash
# Run all linters (Ruff + ESLint)
make lint

# Run Python and frontend test suites
make test

# Full CI validation pipeline
make ci
```

---

## Fallback & Forward Compatibility Notes

### Caddy Fallback Service
In the unlikely event that a reverse proxy or Next.js development server buffers Server-Sent Events (SSE), a production-grade `Caddyfile` is included at the repository root. A Caddy service is pre-configured in `docker-compose.yml` (disabled by default) to handle raw unbuffered streaming if required.

### Next.js 16 Upgrade Path (`proxy.ts`)
Next.js is currently pinned to `~15.x`. If upgraded to Next.js 16+ in the future, rewrite handling should be migrated to `src/proxy.ts` according to the new server proxy convention.
