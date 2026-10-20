# Mise System Architecture

Mise is a revenue copilot and operational platform for independent restaurants. Guests scan table QR codes to order from an English/Italian web menu with deterministic allergen safety filters. Kitchen staff process orders in real time via a Server-Sent Events (SSE) kitchen display system (KDS). Owners get a revenue brief computed from order history (KPIs, menu engineering, a backtested 7-day demand forecast, ranked actions), a deterministic what-if calculator, and VLM menu digitization. Methods and limits: [analytics.md](analytics.md).

---

## 1. System Architecture

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
    (Relational DB)    (Pub/Sub, Cache)  (OpenAI-Compatible Engine / Mock)
```

### Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend | Two Next.js ~15 applications: `guest-web` + `owner-web` | Isolated bundles: guest ordering footprint remains minimal (< 80 kB initial JS), while owner dashboard and kitchen displays run in separate route groups. |
| API Proxy | Each frontend application rewrites only allowed `/api/*` paths to `http://api:8000` | Eliminates Cross-Origin Resource Sharing (CORS) complexity. Cookies are same-origin. Zero build-time API URLs required. |
| Auth Cookies | Two signed httpOnly cookies: `mise_auth` (owner or staff role) and `mise_guest` (guest session) | Guest sessions are separate from restaurant management. Both use `SameSite=Lax` for QR code scan transitions. |
| Analytics | SQL aggregates over order_item snapshots; forecast chosen by backtest; LLM only narrates | Numbers are reproducible and auditable; the model cannot invent figures. |
| Real-Time Streaming | Redis Pub/Sub + SSE with 15-second heartbeats | Clean push delivery to KDS and guest order tracking without persistent websocket connection overhead or database polling. |
| Allergen Model | Deterministic, server-authoritative evaluation with precedence `contains > unverified > no_declared_match` | Guaranteed safety: avoids generative AI hallucinations in food allergy cross-checks. |
| Order Idempotency | Server-side computed payload SHA-256 hash paired with client `idempotency_key` | Guaranteed exactly-once order creation under mobile network retries. |

---

## 2. Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **ORM & Migrations**: SQLAlchemy 2.0 (asyncpg for runtime async execution, psycopg for sync Alembic migrations)
- **Validation**: Pydantic v2 & Pydantic-Settings
- **Cache & Pub/Sub**: Redis 7 (redis-py async client)
- **HTTP Client**: HTTPX (async client with connection pooling and timeouts)
- **Code Quality**: Ruff (linter & formatter), pytest, pytest-asyncio

### Frontend
- **Framework**: Next.js 15 (App Router, Standalone output)
- **Language**: TypeScript 5.6+
- **Styling**: Tailwind CSS v4 (CSS-first engine via PostCSS)
- **API Client**: openapi-fetch & openapi-typescript (fully type-safe contracts)
- **Testing**: Vitest, React Testing Library, ESLint

### Infrastructure & Services
- **Database**: PostgreSQL 16 Alpine
- **Inference**: OpenAI-compatible endpoint client with local mock server for testing and development
- **Containerization**: Docker Compose with multi-stage Alpine images

---

## 3. Database Schema

All timestamps are stored as `TIMESTAMPTZ`. Primary keys use UUIDv4 generated via `gen_random_uuid()`. Allergen and dietary arrays are defined as `NOT NULL DEFAULT '{}'`.

### EU-14 Mandatory Allergens
```sql
'gluten', 'milk', 'eggs', 'fish', 'crustaceans', 'molluscs',
'tree_nuts', 'peanuts', 'soy', 'celery', 'mustard', 'sesame', 'sulphites', 'lupin'
```

### Table Definitions

#### `restaurant`
Represents an individual restaurant tenant.
- `id` (UUID, PK)
- `name` (TEXT, NOT NULL)
- `slug` (TEXT, UNIQUE NOT NULL)
- `timezone` (TEXT, NOT NULL DEFAULT 'Europe/Rome')
- `currency` (TEXT, NOT NULL DEFAULT 'EUR')
- `active` (BOOLEAN, NOT NULL DEFAULT true)
- `languages` (TEXT[], NOT NULL DEFAULT '{en}')
- `default_language` (TEXT, NOT NULL DEFAULT 'en')
- `created_at`, `updated_at` (TIMESTAMPTZ)

*Check Constraint*: `CHECK ((default_language = ANY(languages)) IS TRUE)`

#### `menu_item`
Catalog of dishes and beverages offered by a restaurant.
- `id` (UUID, PK)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `category` (TEXT, NOT NULL)
- `price` (DECIMAL(10,2), NOT NULL, `CHECK (price >= 0)`)
- `unit_cost` (DECIMAL(10,2), NOT NULL, `CHECK (unit_cost >= 0)`). *Excluded from guest schemas.*
- `ingredients` (TEXT[], NOT NULL DEFAULT '{}')
- `allergens` (TEXT[], NOT NULL DEFAULT '{}')
- `allergen_verified` (BOOLEAN, NOT NULL DEFAULT false)
- `is_vegetarian`, `is_vegan`, `is_gluten_free` (BOOLEAN, NOT NULL DEFAULT false)
- `dietary_verified` (BOOLEAN, NOT NULL DEFAULT false)
- `available` (BOOLEAN, NOT NULL DEFAULT true)
- `featured` (BOOLEAN, NOT NULL DEFAULT false)
- `sort_order` (INTEGER, NOT NULL DEFAULT 0)
- `image_url` (TEXT, Nullable)
- `deleted_at` (TIMESTAMPTZ, Nullable — soft delete)
- `created_at`, `updated_at` (TIMESTAMPTZ)

*Check Constraints*:
```sql
CHECK (allergens <@ ARRAY['gluten','milk','eggs','fish','crustaceans','molluscs',
       'tree_nuts','peanuts','soy','celery','mustard','sesame','sulphites','lupin']::text[])
CHECK (NOT (is_vegan AND NOT is_vegetarian))
CHECK (NOT (is_gluten_free AND 'gluten' = ANY(allergens)))
CHECK (NOT is_vegan OR NOT (allergens && ARRAY['milk','eggs','fish','crustaceans','molluscs']::text[]))
CHECK (NOT is_vegetarian OR NOT (allergens && ARRAY['fish','crustaceans','molluscs']::text[]))
```

#### `menu_translation`
Localized titles and descriptions for menu items.
- `id` (UUID, PK)
- `menu_item_id` (UUID, FK → menu_item.id ON DELETE CASCADE)
- `language` (TEXT, NOT NULL)
- `name` (TEXT, NOT NULL)
- `description` (TEXT, Nullable)
- `created_at`, `updated_at` (TIMESTAMPTZ)
*Constraint*: `UNIQUE (menu_item_id, language)`

#### `dining_table`
Physical dining tables mapped to unique QR scan tokens.
- `id` (UUID, PK)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `label` (TEXT, NOT NULL)
- `qr_token` (TEXT, UNIQUE NOT NULL)
- `created_at`, `updated_at` (TIMESTAMPTZ)

#### `guest_session`
Transient guest session tracking dietary requirements and table association.
- `id` (UUID, PK)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `table_id` (UUID, FK → dining_table.id ON DELETE SET NULL, Nullable)
- `language` (TEXT, NOT NULL)
- `dietary_preferences` (TEXT[], NOT NULL DEFAULT '{}')
- `allergens_to_avoid` (TEXT[], NOT NULL DEFAULT '{}')
- `expires_at` (TIMESTAMPTZ, NOT NULL)
- `created_at`, `updated_at` (TIMESTAMPTZ)

#### `orders`
Immutable guest order header record.
- `id` (UUID, PK)
- `guest_session_id` (UUID, FK → guest_session.id ON DELETE RESTRICT)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `table_id` (UUID, FK → dining_table.id ON DELETE SET NULL, Nullable)
- `status` (TEXT, NOT NULL DEFAULT 'placed', `CHECK (status IN ('placed', 'bumped', 'cancelled'))`)
- `source` (TEXT, NOT NULL DEFAULT 'live', `CHECK (source IN ('live', 'simulated'))`) — simulated demo orders are always marked
- `total` (DECIMAL(10,2), NOT NULL, `CHECK (total >= 0)`)
- `idempotency_key` (TEXT, NOT NULL)
- `payload_hash` (TEXT, NOT NULL)
- `allergen_conflict_acknowledged` (BOOLEAN, NOT NULL DEFAULT false)
- `allergens_to_avoid` (TEXT[], NOT NULL DEFAULT '{}') — snapshot at order time
- `dietary_preferences` (TEXT[], NOT NULL DEFAULT '{}') — snapshot at order time
- `placed_at` (TIMESTAMPTZ, NOT NULL DEFAULT now())
- `bumped_at` (TIMESTAMPTZ, Nullable)
- `created_at`, `updated_at` (TIMESTAMPTZ)
*Constraint*: `UNIQUE (guest_session_id, idempotency_key)`

#### `order_item`
Immutable line item with allergen disclosures snapshotted at placement time.
- `id` (UUID, PK)
- `order_id` (UUID, FK → orders.id ON DELETE CASCADE)
- `menu_item_id` (UUID, FK → menu_item.id ON DELETE RESTRICT)
- `quantity` (INTEGER, NOT NULL, `CHECK (quantity >= 1 AND quantity <= 20)`)
- `unit_price` (DECIMAL(10,2), NOT NULL, `CHECK (unit_price >= 0)`)
- `unit_cost` (DECIMAL(10,2), NOT NULL, `CHECK (unit_cost >= 0)`)
- `item_name` (TEXT, NOT NULL) — snapshotted in guest language
- `kitchen_name` (TEXT, NOT NULL) — snapshotted in restaurant default language
- `allergens` (TEXT[], NOT NULL DEFAULT '{}') — snapshotted from item
- `allergen_verified` (BOOLEAN, NOT NULL) — snapshotted from item
- `allergen_status` (TEXT, NOT NULL, `CHECK (allergen_status IN ('contains', 'unverified', 'no_declared_match'))`)
- `notes` (TEXT, Nullable, `CHECK (notes IS NULL OR length(notes) <= 500)`)
- `created_at` (TIMESTAMPTZ)

#### `audit_log`
Append-only log for critical compliance and operational events.
- `id` (UUID, PK)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `event_type` (TEXT, NOT NULL)
- `actor` (TEXT, NOT NULL)
- `payload` (JSONB, NOT NULL DEFAULT '{}')
- `created_at` (TIMESTAMPTZ, NOT NULL DEFAULT now())

#### `forecast_run`
One stored demand forecast (see [analytics.md](analytics.md)).
- `id` (UUID, PK)
- `restaurant_id` (UUID, FK → restaurant.id ON DELETE CASCADE)
- `created_at` (TIMESTAMPTZ, NOT NULL DEFAULT now())
- `horizon_days` (INTEGER, NOT NULL, `CHECK (horizon_days >= 1)`)
- `model_name` (TEXT, NOT NULL)
- `metrics` (JSONB, NOT NULL DEFAULT '{}') — backtest WAPE/MAE per method, chosen method, confidence flag, forecast points
- `params` (JSONB, NOT NULL DEFAULT '{}') — history range and order counts used

#### `metrics_sample`
Per-call inference metrics recording latency, token volume, provider label, and cost.
- `id` (UUID, PK)
- `model` (TEXT, NOT NULL)
- `provider` (VARCHAR(50), NOT NULL DEFAULT 'mock')
- `endpoint` (VARCHAR(50), NOT NULL)
- `tokens_in` (INTEGER, NOT NULL)
- `tokens_out` (INTEGER, NOT NULL)
- `latency_ms` (INTEGER, NOT NULL)
- `cost_usd` (FLOAT, Nullable)
- `gpu_seconds` (FLOAT, Nullable)
- `cached_prefix_tokens` (INTEGER, Nullable)
- `rate_limit_info` (JSONB, Nullable)
- `created_at` (TIMESTAMPTZ, NOT NULL DEFAULT now())

---

## 4. Security & Safety Model

### Deterministic Allergen Safety Engine
To guarantee zero hallucinations in dietary safety, allergen checks are completely deterministic:
1. When a guest configures `allergens_to_avoid`, items are evaluated using set operations against the declared EU-14 allergens of the dish.
2. Precedence rule:
   - **`contains`** (Priority 1): If declared allergens intersect with allergens to avoid, status is `contains`.
   - **`unverified`** (Priority 2): If there is no declared intersection, but `allergen_verified` is false, status is `unverified`.
   - **`no_declared_match`** (Priority 3): If there is no intersection and the item is verified. Note: UI explicitly clarifies this is not a clinical guarantee against trace contamination.
3. Order Placement Guard: If any order item evaluates to `contains` or `unverified`, the order placement request must include an explicit acknowledgment payload identifying those item IDs.

### Order Idempotency
- The client passes an `idempotency_key` (UUID generated in client local state).
- The server computes a canonical SHA-256 hash across sorted order line items (item ID, quantity, notes).
- If the same `(guest_session_id, idempotency_key)` is re-sent with the identical payload hash, the server returns the existing order with HTTP `200 OK`.
- If the key is reused with a altered payload, the server rejects with HTTP `409 Conflict`.

### Authentication & Cookies
1. **`mise_guest`**: Signed httpOnly cookie identifying the active guest session (4 hours). `SameSite=Lax`.
2. **`mise_auth`**: Signed httpOnly cookie carrying the `owner` or `staff` role and expiry (8 hours). `SameSite=Lax`.
Both cookies are signed server-side using HMAC-SHA256 with `API_SECRET_KEY`, and `Secure` outside `APP_ENV=dev`.

### Per-IP Rate Limits and Client Address
Per-IP limits (Redis fixed windows, `services/api/src/request_limits.py`):

| Endpoint | Limit |
|---|---|
| `POST /api/auth/login` | 5 failed attempts per 5 minutes |
| `POST /api/auth/demo-login` | 20 per minute |
| `POST /api/restaurants/{slug}/menu-items/ingest` (DEMO_MODE) | 3 per hour |
| `POST /api/restaurants/{slug}/demo/simulate-orders` | 3 per hour |

The client address comes from the TCP peer. Only when the peer is inside `TRUSTED_PROXY_CIDRS`
(JSON list, default `["172.16.0.0/12"]`, the Docker bridge networks the Next.js apps run on) is
`X-Forwarded-For` used: the API walks it from the right and takes the first hop that is not a
trusted proxy, because hops further left were written by the client. Next.js rewrites only set
`X-Forwarded-For` when the browser did not send one, so behind the Next.js proxy alone a client
can still choose its own address; put a proxy that appends the real peer (Caddy, a tunnel) in
front for public deployments. If Redis is unreachable the limits fail open and log a warning.

### Free-Only Policy & Rate Limits
- Non-local inference calls enforce a Redis-backed daily ceiling (`LLM_DAILY_REQUEST_CAP`, default 200) keyed by UTC day (`mise:llm:daily_cap:YYYY-MM-DD`).
- When the daily cap or a provider 429 rate limit is reached, the backend cleanly returns HTTP `503` with `detail: "ai_unavailable"`. The revenue brief and what-if never fail on this: they fall back to a template summary.
- The frontend gracefully hides real-time chat widgets and displays fallback status badges without disrupting core ordering and kitchen operations.

---

## 5. API Endpoints

### Health & Diagnostics
- `GET /health` — Verifies PostgreSQL and Redis connectivity.
- `GET /debug/sse` — Diagnostic unbuffered SSE counter stream.

### Authentication
- `POST /api/auth/login` — Authenticates owner (API key) or staff (PIN). Sets signed cookie. Rate-limited.
- `POST /api/auth/demo-login` — Fast-path login available when `DEMO_MODE=true`.
- `POST /api/auth/logout` — Clears authentication cookies.
- `GET /api/auth/me` — Returns the current role.
- `GET /api/auth/config` — Returns public environment flags (e.g. `demo_mode`).
- `GET /api/demo/info` — Demo guest, owner and kitchen links (`DEMO_MODE` only).

### Guest Ordering (`guest-web`)
- `POST /api/guest/sessions` — Initializes guest session from table QR token and dietary preferences.
- `GET /api/guest/session` — Returns the active session.
- `PATCH /api/guest/session` — Updates active session preferences and language.
- `GET /api/guest/menu` — Localized menu with dynamic allergen status flags. Excludes `unit_cost`.
- `POST /api/orders` — Idempotent order placement with mandatory allergen acknowledgment checks.
- `GET /api/orders/{id}` — Order status retrieval.
- `GET /api/orders/{id}/stream` — Real-time order progress via SSE.
- `POST /api/guest/chat` — Menu chat assistant (menu context only; the guest's allergen and dietary profile is never sent to the model).

### Kitchen Display (`owner-web`)
- `GET /api/restaurants/{slug}/kitchen/orders` — Retrieves active placed orders with allergen snapshot banners.
- `GET /api/restaurants/{slug}/kitchen/stream` — SSE stream of incoming and updated orders.
- `POST /api/restaurants/{slug}/kitchen/orders/{id}/bump` — Idempotently marks ticket complete (`bumped`).
- `POST /api/restaurants/{slug}/kitchen/orders/{id}/recall` — Reopens ticket if executed strictly within 60 seconds of bumping.

### Owner Dashboard (`owner-web`)
- `GET /api/restaurants/{slug}/menu-items` — Menu catalog including `unit_cost` and verification status.
- `PATCH /api/restaurants/{slug}/menu-items/{id}` — Updates menu item fields. Resets verification flags (with audit log) on allergen, ingredient or dietary edits.
- `POST /api/restaurants/{slug}/menu-items/{id}/verify` — Marks allergens and dietary flags verified.
- `DELETE /api/restaurants/{slug}/menu-items/{id}` — Soft-deletes a menu item.
- `GET /api/restaurants/{slug}/tables` — Lists dining tables with QR tokens and guest URLs.
- `POST /api/restaurants/{slug}/menu-items/ingest` — VLM extraction of menu dish data from photograph URLs.
- `GET /api/restaurants/{slug}/ai/brief` — Deterministic revenue brief: KPIs, menu engineering, pairings, peak hours, backtested 7-day forecast, ranked actions; LLM-written or template summary.
- `POST /api/restaurants/{slug}/ai/simulate` — Deterministic what-if (price change, promotion, demand surge) with listed assumptions.
- `POST /api/restaurants/{slug}/demo/simulate-orders` — Replaces simulated demo orders with a seeded synthetic history (`DEMO_MODE` only).
- `POST /api/restaurants/{slug}/demo/reset` — Re-seeds the demo menu and tables (`DEMO_MODE` only).
- `GET /api/metrics/inference` — Aggregated inference metrics, token counts, average latency, and active provider label.
