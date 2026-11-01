# Mise System Architecture

Mise is a revenue copilot and operational platform for independent restaurants. Guests scan table QR codes to order from an English/Italian web menu with deterministic allergen safety filters, pick a size where a dish has sizes, call a waiter and choose how to pay from their phone; counter QRs take pickup orders that reach the kitchen only once paid. Owners and staff sign in with their own accounts and see only the restaurants they belong to; staff watch every table on a live Floor view, confirm payments (guests never settle a bill) and print a sample bill with illustrative sales tax. Kitchen staff process orders in real time via a Server-Sent Events (SSE) kitchen display system (KDS). Owners get a revenue brief computed from order history (KPIs, menu engineering, a backtested 7-day demand forecast, ranked actions), a deterministic what-if calculator, and VLM menu digitization. Methods and limits: [analytics.md](analytics.md).

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
| Accounts | Users with per-restaurant memberships (`owner` or `staff`); every `{slug}` route checks membership through `restaurant_access` and answers 404 to non-members | One installation can host several clients; no owner can tell whether another restaurant exists. |
| Auth Cookies | Two signed httpOnly cookies: `mise_auth` (signed user id) and `mise_guest` (guest session) | Guest sessions are separate from restaurant management. Both use `SameSite=Lax` for QR code scan transitions. |
| Sales tax | Rates as data in `data/tax_rates.json`, a pure `tax_for`, snapshotted on the bill at settle | Rates change by finance act; the file is reviewed in git with its legal source per row. |
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
- `currency` (TEXT, NOT NULL DEFAULT 'EUR'; both demo venues use `PKR`)
- `city` (TEXT, Nullable)
- `tax_jurisdiction` (TEXT, Nullable) — key into `data/tax_rates.json` (`PB` Punjab, `ICT` Islamabad)
- `pickup_prefix` (TEXT, Nullable) — counter pickup labels print as `<prefix>-042` (1–3 capital letters; `P` Angeethi House, `K` Kehwa & Crumb)
- `service_extra_label` (TEXT, Nullable) — the venue's third Call waiter reason ("More naan / roti")
- `payment_details` (JSONB, NOT NULL DEFAULT '{}') — `raast_id`, `jazzcash`, `easypaisa`, `iban`, `account_title`, `sample`; validated on save (§4)
- `onboarding` (JSONB) — includes the venue's `simulation` profile for demo data
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
- `is_pay_forward` (BOOLEAN, NOT NULL DEFAULT false) — the pay-it-forward chai; a partial unique index `uq_menu_item_pay_forward` allows at most one live such item per venue
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

#### `menu_item_option`
Sizes or portions of a dish (e.g. "½ kg" / "1 kg", "Regular" / "Large"). A dish with options keeps `menu_item.price` and `unit_cost` equal to its cheapest option.
- `id` (UUID, PK)
- `menu_item_id` (UUID, FK → menu_item.id ON DELETE CASCADE)
- `label` (TEXT, NOT NULL), `price`, `unit_cost` (DECIMAL(10,2), NOT NULL, `>= 0`), `sort_order` (INTEGER)
- `created_at`, `updated_at` (TIMESTAMPTZ)
*Constraint*: `UNIQUE (menu_item_id, label)`

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
- `kind` (TEXT, NOT NULL DEFAULT 'table', `CHECK (kind IN ('table','counter'))`) — a `counter` QR takes pickup orders
- `cleared_at` (TIMESTAMPTZ, Nullable) — set by "Mark cleared" on the Floor view
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
- `status` (TEXT, NOT NULL DEFAULT 'placed', `CHECK (status IN ('awaiting_payment', 'placed', 'bumped', 'cancelled'))`) — counter orders start `awaiting_payment` and become `placed` when their bill is settled; voided orders are `cancelled`
- `source` (TEXT, NOT NULL DEFAULT 'live', `CHECK (source IN ('live', 'simulated', 'pay_forward'))`) — simulated demo orders are always marked; `pay_forward` is a zero-price handout ticket with no bill
- `total` (DECIMAL(10,2), NOT NULL, `CHECK (total >= 0)`)
- `bill_id` (UUID, FK → bills.id, Nullable) — the table bill the order joined
- `idempotency_key` (TEXT, NOT NULL)
- `payload_hash` (TEXT, NOT NULL)
- `allergen_conflict_acknowledged` (BOOLEAN, NOT NULL DEFAULT false)
- `allergens_to_avoid` (TEXT[], NOT NULL DEFAULT '{}') — snapshot at order time
- `dietary_preferences` (TEXT[], NOT NULL DEFAULT '{}') — snapshot at order time
- `placed_at` (TIMESTAMPTZ, NOT NULL DEFAULT now())
- `bumped_at` (TIMESTAMPTZ, Nullable)
- `voided_at`, `voided_by` (FK → users.id), `void_reason` — staff void; `CHECK (voided_at IS NULL OR status = 'cancelled')`
- `void_kind` — `staff` | `declined` | `table_closed`; the guest's cancel reason comes from this, never from the free-text `void_reason`
- `collected_at`, `collected_by` (FK → users.id) — counter pickup handed over; `CHECK (collected_at IS NULL OR status = 'bumped')`
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
- `option_id` (UUID, FK → menu_item_option.id, Nullable), `option_label` (TEXT, Nullable) — chosen size, snapshotted; price and cost come from the option on the server
- `item_name` (TEXT, NOT NULL) — snapshotted in guest language
- `kitchen_name` (TEXT, NOT NULL) — snapshotted in restaurant default language
- `allergens` (TEXT[], NOT NULL DEFAULT '{}') — snapshotted from item
- `allergen_verified` (BOOLEAN, NOT NULL) — snapshotted from item
- `allergen_status` (TEXT, NOT NULL, `CHECK (allergen_status IN ('contains', 'unverified', 'no_declared_match'))`)
- `notes` (TEXT, Nullable, `CHECK (notes IS NULL OR length(notes) <= 500)`)
- `is_pay_forward` (BOOLEAN, NOT NULL DEFAULT false) — the item's flag when ordered; settling credits this snapshot, not the current flag
- `created_at` (TIMESTAMPTZ)

#### `users`
- `id` (UUID, PK), `email` (TEXT, UNIQUE, stored lower-case), `name` (TEXT)
- `password_hash` (TEXT) — stdlib scrypt with a random 16-byte salt: `scrypt$n$r$p$salt$hash`
- `created_at`, `updated_at` (TIMESTAMPTZ)

#### `memberships`
- `id` (UUID, PK), `user_id` (FK → users.id), `restaurant_id` (FK → restaurant.id)
- `role` (TEXT, `CHECK (role IN ('owner', 'staff'))`)
*Constraint*: `UNIQUE (user_id, restaurant_id)`

#### `bills`
One bill per table visit, or one per counter order. Placing a table order joins the table's open bill or opens one; each counter order opens its own bill (no `table_id`).
- `id` (UUID, PK), `restaurant_id` (FK), `table_id` (FK, Nullable)
- `bill_no` (INTEGER, Nullable) — per-venue sequence, assigned at open under a per-restaurant advisory lock; required for live bills, NULL for simulated ones. *Constraint*: `UNIQUE (restaurant_id, bill_no)`
- `status` (`open` | `settled` | `cancelled`) — a partial unique index allows one open bill per table; a cancelled bill needs `cancelled_at`
- `pickup_day` (DATE), `pickup_no` (INTEGER) — counter bills only, both or neither; numbered per venue per local day from 1 under the advisory lock, never wrapping. *Constraint*: `UNIQUE (restaurant_id, pickup_day, pickup_no)`
- `source` (`live` | `simulated`)
- `bill_requested_at` (TIMESTAMPTZ, Nullable) — set by the guest's first payment claim (or `POST /api/guest/bill-request`)
- `claimed_method`, `claimed_reference` (≤ 64 chars), `claimed_total`, `claimed_at` — the guest's latest payment claim; never settles
- `settled_by` (FK → users.id), `cancelled_at`, `cancelled_by` (FK → users.id), `cancel_reason`
- `payment_method` (`cash`, `card`, `wallet`, `raast`, `bank_transfer`), `payment_reference` (max 64 chars)
- `subtotal`, `tax_jurisdiction`, `tax_rate`, `tax_amount`, `total` — snapshotted at settle
- `opened_at`, `settled_at`, `created_at`, `updated_at` (TIMESTAMPTZ)

#### `service_call`
A guest's Call waiter.
- `id` (UUID, PK), `restaurant_id` (FK), `table_id` (FK → dining_table.id)
- `reason` (TEXT, `CHECK (reason IN ('help','water','extra'))`)
- `created_at`, `resolved_at` (TIMESTAMPTZ), `resolved_by` (FK → users.id)
*Constraint*: partial unique index on `table_id` where `resolved_at IS NULL` (one open call per table)

#### `pay_forward`
Ledger of pay-it-forward chai. Balance = Σ `bought` − Σ `given`, never below zero (the give takes a lock before checking it).
- `id` (UUID, PK), `restaurant_id` (FK)
- `kind` (`bought` | `given`), `quantity` (INTEGER, `> 0`)
- `order_id` (FK → orders.id, Nullable) — the paid order (`bought`) or the handout ticket (`given`)
- `user_id` (FK → users.id, Nullable) — who gave it
- `idempotency_key` (TEXT, Nullable) — on `given` rows; *Constraint*: `UNIQUE (restaurant_id, idempotency_key)`
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
- The server computes a canonical SHA-256 hash across sorted order line items (item ID, option ID, quantity, notes).
- If the same `(guest_session_id, idempotency_key)` is re-sent with the identical payload hash, the server returns the existing order with HTTP `200 OK`.
- If the key is reused with a altered payload, the server rejects with HTTP `409 Conflict`.

### Authentication & Cookies
1. **`mise_guest`**: Signed httpOnly cookie identifying the active guest session (4 hours). `SameSite=Lax`.
2. **`mise_auth`**: Signed httpOnly cookie carrying the user id and expiry (8 hours). `SameSite=Lax`. No role is stored in the cookie: the role comes from the user's membership in the restaurant being accessed.
Both cookies are signed server-side using HMAC-SHA256 with `API_SECRET_KEY`, and `Secure` outside `APP_ENV=dev`.

### Accounts and Restaurant Isolation
- `POST /api/auth/login` takes email and password; unknown email and wrong password give the same 401.
- `restaurant_access(roles)` loads the restaurant and the caller's membership in one query. No membership or an unknown slug → 404 "Restaurant not found" (identical); member with the wrong role (staff on an owner-only route) → 403. The kitchen SSE stream checks access before subscribing. An API test walks the route table and asserts the 404 across venues for every `{slug}` route.
- There is no public sign-up. Clients are onboarded with `scripts/admin.py`:
  ```bash
  docker compose exec api python scripts/admin.py create-restaurant \
      --slug cafe-x --name "Cafe X" --city Lahore --jurisdiction PB --currency PKR --timezone Asia/Karachi
  docker compose exec api python scripts/admin.py add-user \
      --email boss@cafex.pk --name Boss --restaurant cafe-x --role owner
  ```
  `create-restaurant` rejects a jurisdiction with no tax rates; `add-user` prompts for the password (never taken from argv or printed) and only adds a membership for an existing user.
- Demo users (seeded only when `DEMO_MODE=true`, `data/seed/demo_users.json`): a demo owner of both demo venues and one demo staff user per venue. `POST /api/auth/demo-login {role, venue?}` signs in as one of them and is disabled outside demo mode.

### Bills and Sales Tax
- Payment classes: `card`, `wallet` (JazzCash / Easypaisa) and `raast` (Raast QR) are `digital`; `cash` and `bank_transfer` are `standard`.
- `data/tax_rates.json` lists rates per jurisdiction, payment class and `effective_from` date, each with its legal source: Punjab (`PB`) 16% standard / 8% digital from 2026-07-01 (16% / 5% from 2025-07-01, Punjab Sales Tax on Services Act 2012 as amended by the Punjab Finance Act 2026); Islamabad (`ICT`) 15% / 5% (ICT Tax on Services Ordinance 2001). The ICT law is silent on bank transfer; the standard rate is our assumption. Verification notes: `docs/research/2026-10-24-tax-rate-verification.md`.
- The file is validated at startup (rates in [0, 1], known classes, unique jurisdiction/class/date); an invalid file stops the API. `tax_for(jurisdiction, payment_method, on_date, subtotal)` is pure: latest entry with `effective_from <= on_date`, amount rounded half-up to whole rupees, once per bill.
- Settling snapshots subtotal, rate, tax and total on the bill and records `settled_by`. It requires `expected_total` and `expected_method`: the server recomputes the total under the bill's row lock and answers 409 `{"detail": "Bill changed", "bill": <fresh bill>}` on any difference (a new order, a void, a rate change at midnight). `expected_method` must equal `payment_method` (422 otherwise), so a method switched after the total was read is refused rather than settled. 409 "Bill already settled" / "Bill is not open"; 422 if the bill has no active orders or no tax rate applies (the bill stays open).
- Events on the venue's kitchen channel `kitchen:{restaurant_id}` (payloads carry ids only): `order_placed`, `order_bumped`, `order_recalled`, `order_voided`, `order_collected`, `order_uncollected`, `bill_opened`, `bill_requested`, `bill_settled`, `bill_cancelled`, `payment_claimed`, `service_call_opened`, `service_call_resolved`, `table_cleared`, `pay_forward_given`. The kitchen display, Floor view and Bills page all reload from this one stream; guests' order pages listen on `orders:{order_id}`. SSE responses carry `Cache-Control: no-cache, no-transform` so the Next.js proxies (which gzip responses) and other proxies pass events through unbuffered.
- The printable bill is a **sample bill**: its footer always reads "Sample bill — not a tax invoice. Not connected to FBR or any provincial revenue authority." It has no fiscal number, QR code or authority logo, and the tax line is labelled "illustrative".

### Table Self-Service, Counter Pickup and Money Safeguards
Guests never settle bills; every settle carries the expected total and method and is refused on mismatch.

- **Claims**: `POST /api/guest/bill/payment {method, reference?}` stores `claimed_*` and `bill_requested_at` and never settles. A reference is required for wallet, raast and bank_transfer (1–64 ASCII letters, digits, spaces or `_ - . / #`; otherwise 422). The bill is locked, so a repeated identical claim (a retry after a dropped connection) records nothing new; a different method or reference replaces the claim (latest wins).
- **Floor state** is one pure function `table_state(facts, now)` (`services/api/src/services/floor.py`) fed by one query per venue; thresholds seated 3/5, ordered 12/18, paying 3/5, needs clearing 2/5 minutes (amber/red); an open call is red at once.
- **Counter orders**: a counter QR (`dining_table.kind='counter'`) opens one bill per order with the next `pickup_no` for the venue's local day; the order waits in `awaiting_payment` (never on the kitchen display) until a staff settle flips it to `placed` and publishes `order_placed`. When the open counter list is read, unpaid and unclaimed counter orders older than 30 minutes are cancelled with their bills (`cancel_reason` "Expired unpaid"), under row locks with `SKIP LOCKED`, so a settle or claim in progress wins. Collected can be undone within 60 s.
- **Pay-it-forward**: settling a bill writes one `bought` row per pay-it-forward line, from the `order_item.is_pay_forward` snapshot. `POST …/pay-forward/give {quantity: 1, idempotency_key}` takes the venue lock, refuses with 409 "None waiting" at balance 0, and writes a `given` row and a zero-price `source='pay_forward'` order for the kitchen; a retry with the same key returns the first handout.

Safeguards (zero margin for money errors):
1. **Claimed total**: the claim stores `claimed_total`; if the bill later differs, staff see "Guest sent Rs A · bill is now Rs B · Rs … still due" (or "overpaid").
2. **Expected total on settle**: 409 with the fresh bill when the recomputed total or method differs from what staff saw.
3. **Reused reference**: a reference (staff-typed or the guest's claim) already used or claimed on another settled or cancelled bill of the venue in the last 7 days, or claimed on another open bill, is flagged; settling then needs `acknowledge_reused_reference: true` (409 "Reference already used on Bill NNNN" otherwise).
4. **No auto-settle**: nothing settles without a staff action, and the confirm sheet tells staff to check their banking or wallet app. The demo cannot verify a transaction with a bank.
5. **Device labels and voids**: orders on a table bill carry "Phone n" by each guest session's first order; a session whose first order lands on a bill open for more than 20 minutes is flagged "Joined late". Staff void `placed` or `bumped` orders on an open bill with a reason; voiding the last active order cancels the bill, and needs `acknowledge_claim` when the guest says they paid. Voided items are shown to the guest.
6. **Accountability**: settle, void, cancel, collect, uncollect, clear, resolve and give record the user (`settled_by`, `voided_by`, `cancelled_by`, `collected_by`, `resolved_by`, `pay_forward.user_id`) and an `audit_log` row.
7. **Expiry vs claims**: expiry skips claimed bills; cancelling a claimed counter bill requires a reason and shows "Guest said they paid by … — any refund happens outside Mise." A guest claim on an order that expired the same day revives it.
8. **Collect undo** within 60 s; collecting an order that is not bumped is refused (409).
9. **Payment detail validation** (`services/api/src/services/payment_details.py`): IBAN `PK` + 2 check digits + 4 letters + 16 digits with the mod-97 checksum; JazzCash and Easypaisa `03` + 9 digits (`+92`, `0092` and `92` prefixes normalised); Raast ID a mobile number or IBAN; account title 2–80 characters without control or direction characters, required with any method field. `sample: true` placeholders are allowed only on demo venues; 422 names the bad field.
10. **Pickup numbers** unique per venue per day (`UNIQUE (restaurant_id, pickup_day, pickup_no)`), no wrap; uncollected orders from an earlier day are tagged "Yesterday".
11. **Pay-forward balance** never below zero (locked check before each give); handouts are not revenue.
12. **Privacy**: payment references and details never reach the language model or the brief facts.

Other refusals: a stale guest session (the table was settled, cleared or its bill cancelled since the scan) gets 409 "Your visit has ended — scan the table QR again" when it orders, calls or pays, while its own settled bill stays readable; Mark cleared answers 409 "Settle the bill first" with an open bill and "New guests are already seated" unless `force` (audited); a second open call is 409 and a call within 60 s of the previous one 429; a call from a counter session is 422.

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
`X-Forwarded-For` when the browser did not send one, so behind the Next.js apps alone (ports
3000/3001) a client can choose its own address. For public deployments run the edge proxy,
`docker compose --profile edge up -d`, and expose only its ports (8080 guest, 8081 owner):
Caddy discards client-sent `X-Forwarded-For` and sets the real peer address, which
`make verify-f` checks. Locally, traffic through published Docker ports arrives from the bridge
gateway (e.g. `172.18.0.1`), so all local visitors share one bucket. If Redis is
unreachable the limits fail open and log a warning.

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
- `POST /api/auth/login` — Authenticates a user by email and password (scrypt hash). Sets a signed cookie carrying the user id. Rate-limited.
- `POST /api/auth/demo-login` — Signs in the seeded demo owner or venue staff user when `DEMO_MODE=true`.
- `POST /api/auth/logout` — Clears authentication cookies.
- `GET /api/auth/me` — Returns the signed-in user's name and email.
- `GET /api/restaurants` — Lists the restaurants the signed-in user belongs to, with their role. Every `/api/restaurants/{slug}/...` route returns 404 to non-members.
- `GET /api/auth/config` — Returns public environment flags (e.g. `demo_mode`).
- `GET /api/demo/info` — Owner and kitchen links and, per demo venue, a table QR token and guest link (`DEMO_MODE` only).

### Guest Ordering (`guest-web`)
- `POST /api/guest/sessions` — Initializes guest session from table QR token and dietary preferences.
- `GET /api/guest/session` — Returns the active session, its `table_state` (`open`, `waiting` for a waiter to open the table, `closed` for a phone that ordered on a visit that has ended, `ended` for a phone scanned before the last reset) and whether the table number is still needed (`code_required`).
- `PATCH /api/guest/session` — Updates active session preferences and language.
- `GET /api/guest/menu` — Localized menu with dynamic allergen status flags. Excludes `unit_cost`.
- `POST /api/orders` — Idempotent order placement with mandatory allergen acknowledgment checks.
- `GET /api/orders/{id}` — Order status retrieval.
- `GET /api/orders/{id}/stream` — Real-time order progress via SSE.
- `POST /api/guest/chat` — Menu chat assistant (menu context only; the guest's allergen and dietary profile is never sent to the model).

- `POST /api/guest/bill-request` — Asks for the table's open bill (idempotent; 404 when there is none).
- `GET /api/guest/bill?order_id=` — The order's bill (else the table's open bill or the session's latest): lines, per-method previews, payment details with the `sample` flag, the current claim, voided lines, pickup label and order status, pay-it-forward count once settled.
- `POST /api/guest/bill/payment?order_id=` — `{method, reference?}`: records the guest's payment claim (§4).
- `POST /api/guest/service-calls` — `{reason: help|water|extra}`: Call waiter (tables only).
- `GET /api/guest/service-calls/current` — The open call (if any), whether a waiter can be called, the extra reason and `server_time`.

### Bills (`owner-web`, staff and owner)
- `GET /api/restaurants/{slug}/bills?status=open|settled|cancelled&kind=table|counter` — Open bills (requested first) or the 50 latest settled or cancelled bills, with table or pickup label, bill number, order count, running subtotal and claim; reading open counter bills runs the 30-minute expiry. `status=settled&kind=counter&queue=true` is the counter queue (paid orders preparing, ready, or collected within the undo window).
- `GET /api/restaurants/{slug}/bills/{id}` — Lines grouped by dish and size, subtotal, and server-computed previews for cash or bank transfer vs card, wallet or QR; settled bills return their snapshot.
- `POST /api/restaurants/{slug}/bills/{id}/settle` — `{payment_method, payment_reference?, expected_total, expected_method, acknowledge_reused_reference?}`; snapshots tax and total, or 409 with the fresh bill.
- `POST /api/restaurants/{slug}/bills/{id}/cancel` — `{reason?}`: unpaid counter bills only (reason required when claimed).
- `POST /api/restaurants/{slug}/orders/{id}/void` — `{reason, acknowledge_claim?}`: orders on an open bill.
- `POST /api/restaurants/{slug}/orders/{id}/collect`, `…/uncollect` — counter pickup handed over, and its undo within 60 s.

### Floor (`owner-web`, staff and owner)
- `GET /api/restaurants/{slug}/floor` — One tile per table (state, level, since, call, running total, bill), red and amber counts, thresholds, `server_time` and the pay-it-forward balance.
- `POST /api/restaurants/{slug}/tables/{id}/clear` — `{force?}`: Mark cleared.
- `POST /api/restaurants/{slug}/service-calls/{id}/resolve` — Done.
- `POST /api/restaurants/{slug}/pay-forward/give` — `{quantity: 1, idempotency_key}`: hand out one chai.

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
- `GET /api/restaurants/{slug}/tables` — Lists dining tables and the counter QR (`kind`) with QR tokens and guest URLs.
- `GET`, `PATCH /api/restaurants/{slug}/settings` — Payment details, pickup prefix and extra call reason (§4 validation; 409 when the prefix changes while counter orders are open).
- `POST /api/restaurants/{slug}/menu-items/ingest` — VLM extraction of menu dish data from photograph URLs.
- `GET /api/restaurants/{slug}/ai/brief` — Deterministic revenue brief: KPIs, menu engineering, pairings, peak hours, backtested 7-day forecast, ranked actions; LLM-written or template summary.
- `POST /api/restaurants/{slug}/ai/simulate` — Deterministic what-if (price change, promotion, demand surge) with listed assumptions.
- `POST /api/restaurants/{slug}/demo/simulate-orders` — Replaces simulated demo orders and bills with a seeded synthetic history from the venue's simulation profile; returns `bills_created` (`DEMO_MODE` and a configured demo venue only; 404 otherwise).
- `POST /api/restaurants/{slug}/demo/reset` — Re-seeds the demo menu and tables (`DEMO_MODE` and a configured demo venue only; 404 otherwise).
- `GET /api/metrics/inference` — Aggregated inference metrics, token counts, average latency, and active provider label. Samples are not attributed to a restaurant, so this is an installation-wide operator diagnostic: it answers 404 unless `DEMO_MODE=true`, and is never available on a real multi-venue installation.
