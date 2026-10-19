# Mise System Architecture

Mise is a revenue copilot and operational platform for independent restaurants. Guests scan table QR codes to access an interactive, multi-lingual web ordering experience with deterministic allergen safety filters. Kitchen staff process orders in real time via an unbuffered Server-Sent Events (SSE) kitchen display system (KDS). Restaurant owners access operational intelligence, sales forecasts, scenario simulations, and automated menu digitization.

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
| Auth Cookies | Three distinct signed httpOnly cookies: `mise_owner`, `mise_staff`, `mise_guest` | Role-isolated sessions. Guest cookie uses `SameSite=Lax` for table QR code scan transitions. |
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
1. **`mise_guest`**: Signed httpOnly cookie identifying the active guest session. `SameSite=Lax`.
2. **`mise_owner`**: Signed httpOnly cookie for restaurant management access. `SameSite=Strict`.
3. **`mise_staff`**: Signed httpOnly cookie for kitchen display terminal operation. `SameSite=Strict`.
All cookies are signed server-side using HMAC-SHA256 with `API_SECRET_KEY`.

### Free-Only Policy & Rate Limits
- Non-local inference calls enforce a Redis-backed daily ceiling (`LLM_DAILY_REQUEST_CAP`, default 200) keyed by UTC day (`mise:llm:daily_cap:YYYY-MM-DD`).
- When the daily cap or a provider 429 rate limit is reached, the backend cleanly returns HTTP `503` with `detail: "ai_unavailable"`.
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
- `GET /api/auth/me` — Returns current role and restaurant slug.
- `GET /api/auth/config` — Returns public environment flags (e.g. `demo_mode`).

### Guest Ordering (`guest-web`)
- `POST /api/guest/session` — Initializes guest session from table QR token and dietary preferences.
- `PATCH /api/guest/session` — Updates active session preferences and language.
- `GET /api/guest/menu` — Localized menu with dynamic allergen status flags. Excludes `unit_cost`.
- `POST /api/orders` — Idempotent order placement with mandatory allergen acknowledgment checks.
- `GET /api/orders/{id}` — Order status retrieval.
- `GET /api/orders/{id}/stream` — Real-time order progress via SSE.
- `POST /api/guest/chat` — Contextual concierge chat assistant.

### Kitchen Display (`owner-web`)
- `GET /api/restaurants/{slug}/kitchen/orders` — Retrieves active placed orders with allergen snapshot banners.
- `GET /api/restaurants/{slug}/kitchen/stream` — SSE stream of incoming and updated orders.
- `POST /api/restaurants/{slug}/kitchen/orders/{id}/bump` — Idempotently marks ticket complete (`bumped`).
- `POST /api/restaurants/{slug}/kitchen/orders/{id}/recall` — Reopens ticket if executed strictly within 60 seconds of bumping.

### Owner Dashboard (`owner-web`)
- `GET /api/restaurants/{slug}/menu` — Comprehensive menu catalog including dish unit margins and verification status.
- `POST /api/restaurants/{slug}/menu` — Creates new menu item with default translations.
- `PUT /api/restaurants/{slug}/menu/{id}` — Updates menu item details. Resets verification flags on ingredient edits.
- `DELETE /api/restaurants/{slug}/menu/{id}` — Soft-deletes a menu item.
- `GET /api/restaurants/{slug}/tables` — Lists dining tables with QR tokens and table labels.
- `POST /api/restaurants/{slug}/tables` — Creates dining table and QR token.
- `GET /api/restaurants/{slug}/ai/brief` — Generates daily operational brief and sales curve projections.
- `POST /api/restaurants/{slug}/ai/simulate` — Simulates rush-hour scenarios and throughput bottlenecks.
- `POST /api/restaurants/{slug}/menu-items/ingest` — VLM extraction of menu dish data from photograph URLs.
- `GET /api/metrics/inference` — Aggregated inference metrics, token counts, average latency, and active provider label.
