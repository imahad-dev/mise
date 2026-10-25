# Table Self-Service, Counter Pickup, Floor View and Pay-It-Forward Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `docs/superpowers/specs/2026-10-25-table-self-service-floor-view-design.md`: guests call a waiter and choose/report payment from their phone, staff confirm every rupee, counter pickup with daily numbers, a live Floor view with timing alerts, and a pay-it-forward chai — with zero tolerance for money errors.

**Architecture:** Four demo-ready slices, each with its own migration and green suite: (1) service calls + Floor view (pure `table_state` over existing facts), (2) payment claims + hardened settle (`expected_total`/`expected_method`, reused-reference check, voids, device labels, validated payment details), (3) counter pickup (counter tables, one bill per counter order, `awaiting_payment` held from the kitchen until settle, expiry, collect/undo), (4) pay-it-forward ledger. Events reuse the `kitchen:{restaurant_id}` SSE channel.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, Postgres 16, Redis 7, Next.js 15, Tailwind v4, Vitest, Playwright.

---

## Conventions for every task

- Branch `feat/pakistan-foundation` (continue on it; nothing is merged). Never commit to `main`.
- Real table names: `restaurant`, `dining_table`, `menu_item`, `menu_item_option`, `menu_translation`, `guest_session`, `order_item`, `audit_log`, `orders`, `bills`, `users`, `memberships`. New: `service_call`, `pay_forward`.
- Shell is Git Bash. For `make`: `export PATH="/c/Users/MSI/AppData/Local/Temp/claude/C--Users-MSI-Source-Code-Mise/e8eee3b8-2d67-4900-b83b-437f0a538543/scratchpad/bin:$PATH"`.
- Python tests: `docker compose --profile test build api-test && docker compose --profile test run --rm api-test pytest tests/<file>.py -v`; full suite `docker compose --profile test build api-test && docker compose --profile test run --rm api-test`. Drift: `docker compose --profile test run --rm api-test sh -c "alembic upgrade head && alembic check"`. Ruff: `uv run --project services/api ruff check services/ scripts/ && uv run --project services/api ruff format --check services/ scripts/`. TS: `pnpm -r test`, `pnpm --filter <app> lint`, `pnpm --filter <app> exec tsc --noEmit`. Docker Desktop must be running (`docker info`); start it with PowerShell `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"` if not.
- Never read/print `.env`; never run `printenv`, `env`, `docker compose config`; `LLM_PROVIDER=mock` for any stack.
- Rules: relationships `lazy="raise"`, explicit queries, every route has `response_model`, staff routes use `owner_access`/`member_access` from `src/access.py`, guest routes use `get_current_guest_session`, Decimal money, use `status.HTTP_422_UNPROCESSABLE_CONTENT`, publish events only after commit, payloads carry ids only. Models match migrations exactly (`alembic check`).
- Tests helpers: `tests/helpers.py` (`make_user`, `sign_in`, `as_member`); guest cookie via `sign_value(str(session.id))` into `GUEST_COOKIE_NAME`; concurrency tests copy the committed-data pattern in `tests/test_bills.py::test_parallel_settle_and_order`.
- Never weaken/skip/xfail tests; if an existing test changes because behaviour changed, say so in the commit body. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The isolation test (`tests/test_restaurant_isolation.py`) covers every new `{slug}` route automatically; add any new id placeholder names (`table_id`, `call_id`, `order_id`, `bill_id`) to its `DUMMY` map.

## File map (new)

- API: `src/models/service_call.py`, `src/models/pay_forward.py`, `src/services/floor.py`, `src/services/payment_details.py`, `src/services/counter.py`, `src/services/pay_forward.py`, `src/routers/floor.py`, `src/schemas/floor.py`, `src/schemas/payments.py`; migrations `0011_service_calls`, `0012_payment_claims`, `0013_counter_pickup`, `0014_pay_forward`; tests `test_floor_state.py`, `test_floor_api.py`, `test_service_calls.py`, `test_payment_details.py`, `test_payment_claims.py`, `test_settle_safeguards.py`, `test_counter.py`, `test_pay_forward.py`, `test_money_agreement.py`.
- Web: `apps/owner-web/src/app/(dashboard)/floor/page.tsx`, `apps/owner-web/src/lib/floor.ts` (+test), `apps/guest-web/src/components/CallWaiter.tsx`, `apps/guest-web/src/components/PaySheet.tsx`, `apps/guest-web/src/lib/pay.ts` (+test).

---

# Slice 1 — Call waiter and Floor view

### Task 1: Schema for table kind, clearing and service calls

**Files:** Create `src/models/service_call.py`, `alembic/versions/0011_service_calls.py`. Modify `src/models/dining_table.py`, `src/models/restaurant.py`, `src/models/__init__.py`, `data/seed/angeethi_house.json`, `data/seed/kehwa_and_crumb.json`, `scripts/seed.py`. Test: append to `tests/test_schema_constraints.py`, `tests/test_seed.py`.

- [ ] **Step 1: Failing tests**

```python
async def test_service_call_one_open_per_table(db_session):
    from sqlalchemy.exc import IntegrityError
    from src.models.service_call import ServiceCall
    rid = uuid.UUID(await _create_test_restaurant(db_session))
    table = DiningTable(restaurant_id=rid, label="T9", qr_token=f"qr-{uuid.uuid4().hex}")
    db_session.add(table)
    await db_session.flush()
    db_session.add(ServiceCall(restaurant_id=rid, table_id=table.id, reason="water"))
    await db_session.flush()
    db_session.add(ServiceCall(restaurant_id=rid, table_id=table.id, reason="help"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_service_call_reason_checked(db_session):
    from sqlalchemy.exc import IntegrityError
    from src.models.service_call import ServiceCall
    rid = uuid.UUID(await _create_test_restaurant(db_session))
    table = DiningTable(restaurant_id=rid, label="T8", qr_token=f"qr-{uuid.uuid4().hex}")
    db_session.add(table)
    await db_session.flush()
    db_session.add(ServiceCall(restaurant_id=rid, table_id=table.id, reason="pizza"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_table_kind_checked(db_session):
    from sqlalchemy.exc import IntegrityError
    rid = uuid.UUID(await _create_test_restaurant(db_session))
    db_session.add(DiningTable(restaurant_id=rid, label="X", qr_token="qr-x-kind", kind="bar"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

In `test_seed.py`: after seeding, Angeethi's `service_extra_label == "More naan / roti"`, Kehwa's `== "More napkins / cutlery"`.

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Models.**
  - `DiningTable`: `kind: Mapped[str]` Text not null `server_default=text("'table'")` + `CheckConstraint("kind IN ('table','counter')", name="chk_dining_table_kind")`; `cleared_at: Mapped[datetime | None]` timestamptz.
  - `Restaurant`: `service_extra_label: Mapped[str | None]` Text.
  - `ServiceCall` (`service_call`): `id` UUID pk (match house style), `restaurant_id` FK `restaurant.id` CASCADE, `table_id` FK `dining_table.id` CASCADE, `reason` Text, `created_at` (server now), `resolved_at` null, `resolved_by` UUID FK `users.id` SET NULL null; `CheckConstraint("reason IN ('help','water','extra')", name="chk_service_call_reason")`, `Index("uq_service_call_open_per_table", "table_id", unique=True, postgresql_where=text("resolved_at IS NULL"))`, `Index("idx_service_call_restaurant", "restaurant_id", "created_at")`.
  - Seeds: `"service_extra_label"` in each `restaurant` block; `seed.py` upserts it.
- [ ] **Step 4: Migration `0011_service_calls`** (down_revision `0010_bills`) mirroring all of the above; downgrade reverses.
- [ ] **Step 5: Run tests, full suite, drift → green. Commit** `feat(api): table kind and clearing, service calls`.

### Task 2: Pure floor state

**Files:** Create `src/services/floor.py`, `tests/test_floor_state.py`.

- [ ] **Step 1: Failing tests** (pure, no DB):

```python
from datetime import UTC, datetime, timedelta
from src.services.floor import TableFacts, THRESHOLDS, table_state

T0 = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
def m(n): return T0 + timedelta(minutes=n)
def facts(**kw):
    base = dict(table_id="t", label="T1", kind="table", cleared_at=None, last_session_at=None,
                open_bill=False, paying_since=None, oldest_placed_at=None, has_active_orders=False,
                last_settled_at=None, call_reason=None, call_since=None, running_total=None)
    base.update(kw)
    return TableFacts(**base)

def test_free(): assert table_state(facts(), m(0)).state == "free"
def test_seated_levels():
    f = facts(last_session_at=m(0))
    assert table_state(f, m(2)).level == "none"
    assert table_state(f, m(3)).level == "amber"
    assert table_state(f, m(5)).level == "red"
    assert table_state(f, m(5)).state == "seated"
def test_session_before_clear_is_free():
    assert table_state(facts(last_session_at=m(0), cleared_at=m(1)), m(10)).state == "free"
def test_after_settle_is_needs_clearing_not_seated():
    f = facts(last_session_at=m(0), last_settled_at=m(40))
    s = table_state(f, m(42))
    assert (s.state, s.level) == ("needs_clearing", "amber")
    assert table_state(f, m(45)).level == "red"
def test_new_guests_after_settle_are_seated():
    assert table_state(facts(last_settled_at=m(40), last_session_at=m(41)), m(41)).state == "seated"
def test_ordered_from_oldest_placed():
    f = facts(open_bill=True, has_active_orders=True, oldest_placed_at=m(0))
    assert table_state(f, m(12)).level == "amber" and table_state(f, m(18)).level == "red"
def test_served_has_timer_only():
    s = table_state(facts(open_bill=True, has_active_orders=True), m(60))
    assert (s.state, s.level) == ("served", "none")
def test_paying_outranks_ordered():
    f = facts(open_bill=True, has_active_orders=True, oldest_placed_at=m(0), paying_since=m(10))
    s = table_state(f, m(13))
    assert (s.state, s.level) == ("paying", "amber")
def test_dessert_after_paying_is_ordered():
    f = facts(last_settled_at=m(30), open_bill=True, has_active_orders=True, oldest_placed_at=m(35))
    assert table_state(f, m(36)).state == "ordered"
def test_call_overrides_everything_and_is_red():
    s = table_state(facts(open_bill=True, paying_since=m(0), call_reason="water", call_since=m(1)), m(1))
    assert (s.state, s.level, s.reason) == ("called", "red", "water")
def test_counter_tables_are_not_tiles():
    assert table_state(facts(kind="counter"), m(0)) is None
```

- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement**

```python
"""Floor view: one table's state from facts the system already records. Pure."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

State = Literal["free", "seated", "ordered", "served", "paying", "needs_clearing", "called"]
Level = Literal["none", "amber", "red"]
MIN = timedelta(minutes=1)
# Research: docs/research/2026-10-25-floor-view-notes.md (greet ~1 min, entrée 10-15 min,
# turn within 2 min); seated red at 5 min follows the reel that inspired the feature.
THRESHOLDS: dict[str, tuple[timedelta, timedelta]] = {
    "seated": (3 * MIN, 5 * MIN),
    "ordered": (12 * MIN, 18 * MIN),
    "paying": (3 * MIN, 5 * MIN),
    "needs_clearing": (2 * MIN, 5 * MIN),
}


@dataclass(frozen=True)
class TableFacts:
    table_id: str
    label: str
    kind: str
    cleared_at: datetime | None
    last_session_at: datetime | None
    open_bill: bool
    paying_since: datetime | None
    oldest_placed_at: datetime | None
    has_active_orders: bool
    last_settled_at: datetime | None
    call_reason: str | None
    call_since: datetime | None
    running_total: object | None


@dataclass(frozen=True)
class TileState:
    state: State
    since: datetime | None
    level: Level
    reason: str | None = None


def _level(state: str, since: datetime | None, now: datetime) -> Level:
    if since is None or state not in THRESHOLDS:
        return "none"
    amber, red = THRESHOLDS[state]
    age = now - since
    return "red" if age >= red else "amber" if age >= amber else "none"


def _after(a: datetime | None, b: datetime | None) -> bool:
    return a is not None and (b is None or a > b)


def table_state(f: TableFacts, now: datetime) -> TileState | None:
    if f.kind != "table":
        return None
    if f.call_reason is not None:
        return TileState("called", f.call_since, "red", f.call_reason)
    if f.open_bill:
        if f.paying_since is not None:
            return TileState("paying", f.paying_since, _level("paying", f.paying_since, now))
        if f.oldest_placed_at is not None:
            return TileState("ordered", f.oldest_placed_at, _level("ordered", f.oldest_placed_at, now))
        if f.has_active_orders:
            return TileState("served", None, "none")
    reset = max((t for t in (f.cleared_at, f.last_settled_at) if t is not None), default=None)
    if _after(f.last_session_at, reset):
        return TileState("seated", f.last_session_at, _level("seated", f.last_session_at, now))
    if _after(f.last_settled_at, f.cleared_at):
        return TileState("needs_clearing", f.last_settled_at,
                         _level("needs_clearing", f.last_settled_at, now))
    return TileState("free", None, "none")
```

  Note: an open bill with no active orders (all voided) falls through to seated/needs-clearing/free — add a test for it (`open_bill=True, has_active_orders=False, last_session_at=m(0)` → seated).
- [ ] **Step 4: Run → pass. Commit** `feat(api): pure floor state with timing levels`.

### Task 3: Floor and service-call API

**Files:** Create `src/routers/floor.py`, `src/schemas/floor.py`, `tests/test_floor_api.py`, `tests/test_service_calls.py`. Modify `src/routers/guest.py`, `src/main.py`, `tests/test_restaurant_isolation.py` (DUMMY ids).

- [ ] **Step 1: Failing tests.**
  - `test_floor_api.py` (venue fixture with PB, tables T1–T3 and one `kind="counter"` table, menu with Naan): `GET /api/restaurants/{slug}/floor` as staff → 3 tiles (counter excluded) all `free`, `server_time` present, `counts == {"red":0,"amber":0}`; after a guest session on T1 (backdate `created_at` 6 min) → T1 `seated`/`red`, first in the list, counts red 1; after an order → `ordered`; after kitchen bump → `served`; after `bill-request` → `paying`; after settle → `needs_clearing`; `POST …/tables/{id}/clear` → `free`; clearing with an open bill → 409 "Settle the bill first"; another venue's table id under my slug → 404.
  - `test_service_calls.py`: guest `POST /api/guest/service-calls {"reason":"water"}` → 201 with `{id, reason, created_at}`; second call → 409; after staff `POST …/service-calls/{id}/resolve` a new call within 60 s → 429, after backdating `created_at` 61 s → 201; `GET /api/guest/service-calls/current` returns the open call or `{"call": null}`; floor tile `called`/`red` with `reason`; counter-session call → 422; bad reason → 422; resolving another venue's call → 404; resolving twice → 409; each event published (`service_call_opened`, `service_call_resolved`, `table_cleared`) — assert via a monkeypatched `publish_event` that records calls.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement.**
  - `schemas/floor.py`: `FloorTile(table_id, label, state, level, since: datetime|None, reason: str|None, reason_label: str|None, running_total: Decimal|None, bill_id: uuid|None, call_id: uuid|None)`, `FloorResponse(tiles, counts: dict[str,int], thresholds: dict[str, list[int]] (seconds), server_time: datetime, service_extra_label: str|None)`, `ServiceCallRequest(reason: Literal["help","water","extra"])`, `ServiceCallResponse(id, reason, reason_label, created_at, resolved_at)`, `CurrentCallResponse(call: ServiceCallResponse | None)`.
  - `routers/floor.py` (prefix `/api/restaurants/{slug}`, `member_access`):
    - `GET /floor`: one query set — tables of the venue; latest `guest_session.created_at` per table; open bill per table with `bill_requested_at`; min `placed_at` of `placed` orders per open bill; whether active (`status <> 'cancelled'`) orders exist; running total (sum of active order totals); latest `settled_at` per table; open service call per table. Build `TableFacts`, call `table_state`, sort by (red, amber, none) then label (natural sort T1<T2<T10), count levels. `server_time = clock_timestamp()`.
    - `POST /tables/{table_id}/clear`: table scoped by restaurant (404); 409 if an open bill exists; set `cleared_at = clock_timestamp()`; audit `table_cleared` actor `user:{id}`; commit; publish.
    - `POST /service-calls/{call_id}/resolve`: scoped (404); 409 if resolved; set `resolved_at`, `resolved_by`; audit; commit; publish.
  - `routers/guest.py`: `POST /api/guest/service-calls` — 422 if session has no table or table kind is `counter`; 429 if the table's latest call (any state) was created < 60 s ago; insert (IntegrityError on the partial unique → 409 "A waiter is already on the way"); commit; publish `service_call_opened`. `GET /api/guest/service-calls/current`.
  - `reason_label`: help → "Need help", water → "Water, please", extra → restaurant `service_extra_label` or "Something else".
- [ ] **Step 4: Run tests + isolation + full suite → green. Commit** `feat(api): floor view and service calls`.

### Task 4: Floor page, sidebar badge, guest Call waiter

**Files:** Create `apps/owner-web/src/app/(dashboard)/floor/page.tsx`, `apps/owner-web/src/lib/floor.ts` (+`floor.test.ts`), `apps/guest-web/src/components/CallWaiter.tsx`. Modify `(dashboard)/layout.tsx` (nav "Floor" first in Service with a live count badge), guest menu and order pages, guest i18n (`types.ts`, `en.ts`, `it.ts`).

- [ ] **Step 1: Failing tests** `floor.test.ts`: `elapsed(sinceIso, serverTimeIso, clientNowMs, loadedAtMs)` uses the server offset (a client clock 10 min off still gives the right elapsed); `formatElapsed(65_000) === "1:05"`; `stateLabel("seated") === "Seated, no order"`, `"needs_clearing" → "Needs clearing"`, `"called" → "Waiter called"`; `sortTiles` keeps red, amber, none order.
- [ ] **Step 2: Implement.**
  - `floor.ts`: types mirroring `FloorResponse`, the helpers above, `levelClass(level)` mapping to existing tokens (red → danger tokens, amber → warn tokens, none → card).
  - Floor page: `useVenue` + `useSlugRef` guards; load `GET …/floor`; reload on kitchen SSE messages (reuse `use-sse`) and every 30 s; a 1 s ticker re-renders timers; responsive grid of `Card` tiles (label, icon + state text, timer, running total via `formatPrice`, reason); actions per state: `called` → **Done**; `needs_clearing` → **Mark cleared**; tiles with `bill_id` → **Open bill** (`/bills?bill={id}`); stale banner "Reconnecting — last updated 40 s ago" when the last successful load is > 45 s old.
  - Layout: nav item "Floor" with a `Badge` showing `counts.red + counts.amber` (poll `/floor` every 30 s in the layout or share state from the page; simplest: a small hook in the layout polling every 30 s).
  - Guest `CallWaiter`: header outline button "Call waiter" on menu and order pages when the session table is a normal table (the menu API returns `table_label`; add `table_kind` to `GuestMenuResponse` in this task — one-line server change with a test assertion); `Sheet` with the three reasons (third from `service_extra_label`, add it to the menu response too); after calling shows "Waiter called · m:ss"; handles 409/429 with i18n messages; polls `GET /api/guest/service-calls/current` every 15 s while a call is open.
  - i18n keys `call.button`, `call.help`, `call.water`, `call.called`, `call.wait`, `call.already` in en/it/types.
- [ ] **Step 3: Run TS tests, lint, tsc both apps; Python tests for the menu response change. Commit** `feat(web): Floor view and guest Call waiter`.

# Slice 2 — Pay from the table with money safeguards

### Task 5: Schema for claims, voids, settle accountability, payment details

**Files:** Create `alembic/versions/0012_payment_claims.py`. Modify `src/models/bill.py`, `src/models/order.py`, `src/models/restaurant.py`. Test: `tests/test_schema_constraints.py`.

- [ ] **Step 1: Failing tests**: bill with `claimed_reference` of 65 chars → IntegrityError; bill `status='cancelled'` without `cancelled_at` → IntegrityError; settled bill still requires payment fields (existing test stays green); order with `voided_at` but status not `cancelled` → IntegrityError.
- [ ] **Step 2: Implement.**
  - `bills`: `claimed_method` Text null + check in the five methods; `claimed_reference` Text null (≤64 check); `claimed_total` Numeric(10,2) null; `claimed_at` timestamptz null; `settled_by` UUID FK `users.id` SET NULL null; `cancelled_at`, `cancelled_by` (FK users SET NULL), `cancel_reason` Text null. Replace `chk_bills_status` with `status IN ('open','settled','cancelled')`; replace `chk_bills_settled_complete` with `status <> 'settled' OR (payment_method IS NOT NULL AND total IS NOT NULL AND settled_at IS NOT NULL)`; add `chk_bills_cancelled_complete`: `status <> 'cancelled' OR cancelled_at IS NOT NULL`. Partial unique `uq_bills_one_open_per_table` unchanged.
  - `orders`: `voided_at` timestamptz null, `voided_by` UUID FK users SET NULL null, `void_reason` Text null; check `chk_orders_void`: `voided_at IS NULL OR status = 'cancelled'`.
  - `restaurant`: `payment_details` JSONB not null `server_default=text("'{}'::jsonb")`.
- [ ] **Step 3: Migration** mirroring all, downgrade restores the old checks. **Step 4: green + drift. Commit** `feat(api): schema for payment claims, voids and cancellations`.

### Task 6: Payment details validation and owner settings

**Files:** Create `src/services/payment_details.py`, `tests/test_payment_details.py`. Modify `src/routers/owner.py` (PATCH `/settings`), `src/schemas/owner.py`, seeds + `scripts/seed.py`.

- [ ] **Step 1: Failing tests**

```python
import pytest
from src.services.payment_details import PaymentDetailsError, validate_payment_details

GOOD_IBAN = "PK36SCBL0000001123456702"  # standard published example, passes mod-97

def test_valid_details():
    d = validate_payment_details({"raast_id": "03001234567", "jazzcash": "03001234567",
                                  "easypaisa": "03451234567", "iban": GOOD_IBAN.lower(),
                                  "account_title": "Angeethi House"})
    assert d["iban"] == GOOD_IBAN

@pytest.mark.parametrize("field,value", [
    ("iban", "PK36SCBL0000001123456703"),   # checksum fails
    ("iban", "GB36SCBL0000001123456702"),   # not PK
    ("iban", "PK36SCBL00000011234567"),     # too short
    ("jazzcash", "3001234567"), ("easypaisa", "04001234567"), ("raast_id", "hello"),
    ("account_title", "A"),
])
def test_invalid(field, value):
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"account_title": "Venue", field: value})
    assert e.value.field == field

def test_sample_values_allowed_only_when_sample():
    sample = {"sample": True, "raast_id": "0000 SAMPLE", "account_title": "Sample account"}
    assert validate_payment_details(sample)["sample"] is True
    with pytest.raises(PaymentDetailsError):
        validate_payment_details({**sample, "sample": False})
```

  Verify `GOOD_IBAN` passes mod-97 in the test itself (compute) — if it doesn't, generate a valid example by computing check digits in the test helper and use that instead.
- [ ] **Step 2: Implement** `validate_payment_details(raw) -> dict`: keys allowed `raast_id, jazzcash, easypaisa, iban, account_title, sample`; strip spaces/hyphens; mobile = `^03\d{9}$`; IBAN uppercase, `^PK\d{2}[A-Z]{4}\d{16}$` and mod-97 == 1 (move first 4 chars to the end, letters → 10..35); Raast ID = mobile or IBAN; account title 2–80 chars; `sample: True` skips format checks (but keeps length limits) and is required to be shown with the demo banner. `PaymentDetailsError(field, message)`.
- [ ] **Step 3: Owner `PATCH /api/restaurants/{slug}/settings`** (`owner_access`): body `{payment_details?, pickup_prefix?, service_extra_label?}` (pickup_prefix is ignored until Task 10 adds the column — add the field in Task 10 instead, not now). 422 with `{"field": …}` on invalid; in `DEMO_MODE` the `sample` flag is forced true for demo slugs. Response: the saved settings.
- [ ] **Step 4: Seeds**: both venues get `"payment_details": {"sample": true, "raast_id": "0000 SAMPLE", "jazzcash": "0000 SAMPLE", "easypaisa": "0000 SAMPLE", "iban": "PK00 SAMPLE 0000 0000 0000", "account_title": "Sample account — demo only"}`; seeder upserts it.
- [ ] **Step 5: green. Commit** `feat(api): validated venue payment details and owner settings`.

### Task 7: Guest payment claims and the guest bill

**Files:** Create `src/schemas/payments.py`, `tests/test_payment_claims.py`. Modify `src/routers/guest.py`, `src/services/bills.py`.

- [ ] **Step 1: Failing tests** (PB venue, Full karahi 2100 + 4 naan 240 = 2340):
  - `GET /api/guest/bill` → `lines`, `subtotal "2340.00"`, `methods` list with 5 entries `{method, label, payment_class, tax_rate, tax_amount, total}`: cash/bank_transfer 16% → 374/2714; card/wallet/raast 8% → 187/2527; `payment_details` with `sample: true`; `claim: null`; `voided: []`.
  - `POST /api/guest/bill/payment {"method":"raast","reference":"TX123"}` → 200, `claim.method == "raast"`, `claim.total == "2527.00"`, bill `bill_requested_at` set; repeating the identical request → 200 and `claimed_at` unchanged; switching to `{"method":"cash"}` → claim cash, total 2714; `{"method":"wallet"}` without reference → 422; reference with `"\n"` or 65 chars → 422; `"<script>x</script>"` is accepted only if it passes the character rule — define the rule: references allow `[A-Za-z0-9 _\-./#]` 1–64; anything else → 422; claim on a settled bill → 409; no open bill → 404.
  - After staff void one naan order (Task 8 provides void; in this task write the voided-items test in Task 8 instead).
  - Privacy: `GET /api/guest/bill` for session A never shows table B's bill; a guest of venue B gets 404 for anything on venue A.
- [ ] **Step 2: Implement.**
  - `services/bills.py`: `method_previews(jurisdiction, subtotal, on_date) -> list[MethodPreview]` built from `tax_for` for each of the five methods (labels: Cash, Card, JazzCash / Easypaisa, Raast QR, Bank transfer). Reuse `bill_lines`.
  - `schemas/payments.py`: `MethodPreview`, `PaymentClaim(method, reference, total, claimed_at)`, `GuestPaymentRequest(method: Literal[...], reference: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9 _\-./#]{1,64}$"))` with a model validator requiring reference for wallet/raast/bank_transfer; `GuestBillDetail` (existing `GuestBillResponse` fields + `lines`, `subtotal`, `methods`, `payment_details`, `claim`, `voided: list[VoidedLine]`, `currency`, `pickup_label: str | None` (filled in Task 11), `order_status: str | None`, `pay_forward_count: int = 0` (filled in Task 13)).
  - `GET /api/guest/bill` returns `GuestBillDetail` (keep it backward compatible for existing tests: the old fields remain).
  - `POST /api/guest/bill/payment`: lock the session table's open bill `FOR UPDATE` (404 if none, 409 if settled); compute the claimed total from current active orders and `tax_for(method)` on the local date; if method+reference equal the existing claim → return unchanged; else set `claimed_method/reference/total/at = clock_timestamp()` and `bill_requested_at` if null; audit `payment_claimed` (no reference in the audit payload beyond the last 4 chars); commit; publish `payment_claimed`.
- [ ] **Step 3: green. Commit** `feat(api): guests choose and report payment from the table`.

### Task 8: Settle safeguards, voids and device labels

**Files:** Create `tests/test_settle_safeguards.py`, `tests/test_money_agreement.py`. Modify `src/services/bills.py`, `src/routers/bills.py`, `src/schemas/bills.py`, `src/routers/orders.py` (none expected), `src/routers/kitchen.py` (void route lives in bills router: `POST /api/restaurants/{slug}/orders/{order_id}/void`).

- [ ] **Step 1: Failing tests**
  - Settle now requires `expected_total` and `expected_method`; missing → 422. Wrong `expected_total` (e.g. after a new order) → 409 with body `{"detail": "Bill changed", "bill": <fresh BillDetail>}`; wrong `expected_method` vs `payment_method` → 422 (they must match the request); a claim changed after staff loaded the sheet does not block settle if staff's method/total match the server's recomputation for staff's method.
  - Midnight: freeze tax dates by monkeypatching `local_date` — preview on 2026-06-30 (5%), settle on 2026-07-01 with the old expected total → 409; with the fresh total → 200 at 8%.
  - Reused reference: bill A settled with reference "TX1"; bill B claims "TX1"; detail of B has `reused_reference_bill_no == A.bill_no`; settle B with `payment_reference "TX1"` without `acknowledge_reused_reference` → 409 "Reference already used on Bill 0001"; with it → 200. Only same venue, last 7 days.
  - `settled_by` is the confirming user's id; audit `bill_settled` actor `user:{id}`.
  - Claim mismatch in detail: claim at 2527, then a chai is added → `BillDetail.claim_difference == "-…"` style: define `amount_due_after_claim = total_for(claimed_method) - claimed_total` (positive = still due).
  - Void: `POST …/orders/{id}/void {"reason":"Wrong table"}` on an open bill → order `cancelled`, `voided_by`, audit `order_voided`; void on a settled bill → 409; reason empty or > 200 → 422; another venue's order → 404; voiding the last active order → settle 422 "No active orders"; guest `GET /api/guest/bill` shows `voided: [{name, option_label, quantity}]`; kitchen list no longer shows a voided `placed` order.
  - Device labels: two guest sessions order on F1 within 5 minutes → bill detail `orders: [{order_id, device_label: "Phone 1", joined_late: false, …}, {"Phone 2", false}]`; a third session's first order 25 minutes after the bill opened (backdate `opened_at`) → `joined_late: true`.
  - Concurrency (committed data, parallel clients): two staff settle the same bill simultaneously with correct expectations → exactly one 200, one 409; 20 rounds of claim + new order + settle on one table → every settled bill's `total == subtotal + tax_for(method, settle date, subtotal)` and `subtotal == Σ active orders`, no order on a settled bill placed after `settled_at`.
  - `test_money_agreement.py` (pure property test with `random.Random(1234)` over 2,000 cases): random subtotal in whole rupees 0–200,000, random method, jurisdiction PB/ICT, date in 2026-06-25…2026-07-05 → `method_previews` entry == `tax_for` == the staff preview for the same class == the printed-bill math in `apps/owner-web/src/lib/bill.ts` is TS; for TS agreement add a Vitest test that feeds the same fixed vectors (write 50 vectors to `data/test-vectors/tax_vectors.json` from the Python test generator and assert in Vitest that `formatPrice`/percent math displays the API's numbers verbatim, i.e. the UI never recomputes tax).
- [ ] **Step 2: Implement.**
  - `SettleBillRequest`: add `expected_total: Decimal`, `expected_method` (same Literal), `acknowledge_reused_reference: bool = False`; validator: `expected_method == payment_method`.
  - `settle_bill(db, bill_id, restaurant, method, reference, expected_total, user_id, acknowledge_reused)`: after lock + active orders + tax, `if subtotal + tax != expected_total: raise HTTPException(409, {"detail": "Bill changed"})` — the router catches this specific condition to attach the fresh `BillDetail` (raise a small `BillChanged` exception from the service and convert in the router after recomputing detail). Reused reference check: `select bill_no from bills where restaurant_id=… and id<>… and status='settled' and (payment_reference = :ref or claimed_reference = :ref) and settled_at > now - 7 days`. Set `settled_by`.
  - `BillDetail` gains `claim: PaymentClaim | None`, `amount_due_after_claim: Decimal | None`, `reused_reference_bill_no: int | None`, `orders: list[BillOrder]` (`order_id, placed_at, status, device_label, joined_late, lines`), `settled_by_name: str | None`.
  - Device labels: number distinct `guest_session_id` by first `placed_at` on the bill; `joined_late = first order of that session placed_at - bill.opened_at > 20 min` and the session is not Phone 1.
  - Void route in `routers/bills.py` (prefix stays `/api/restaurants/{slug}`; add a second router or widen the prefix carefully so existing bill paths are unchanged): lock the order `FOR UPDATE` scoped by restaurant, lock its bill, 409 unless the bill is open, set `status='cancelled'`, `voided_at`, `voided_by`, `void_reason`; audit; commit; publish `order_voided`.
- [ ] **Step 3: green (full suite; run concurrency tests 3×). Commit** `feat(api): settle requires the expected total; voids, device labels, reused references`.

### Task 9: Pay sheet (guest) and confirm sheet (staff)

**Files:** Create `apps/guest-web/src/components/PaySheet.tsx`, `apps/guest-web/src/lib/pay.ts` (+`pay.test.ts`). Modify the guest order page, i18n files, `apps/owner-web/src/app/(dashboard)/bills/page.tsx`, `apps/owner-web/src/lib/bill.ts` (+tests).

- [ ] **Step 1: Failing tests.**
  - `pay.test.ts`: `needsReference("raast"|"wallet"|"bank_transfer") === true`, cash/card false; `isValidReference` mirrors the server pattern; `claimMessage(claim, dict)` returns the right sentence for each method; `copyText` fallback when `navigator.clipboard` is missing returns false without throwing.
  - `bill.test.ts`: `amountDueText("60.00", "PKR") === "Rs 60 still due"`, negative → "Rs 60 overpaid"; confirm payload builder always includes `expected_total` and `expected_method` taken from the selected method's preview, never from the claim.
- [ ] **Step 2: Implement.**
  - Guest order page: "Pay bill" opens `PaySheet` (lines, subtotal, five method rows with totals and tax rate); choosing cash/card posts the claim immediately and shows the matching message; wallet/raast/bank shows payment details with copy buttons inside the demo banner when `sample`, a reference input (validated client-side with the same pattern), "I've paid" (disabled while posting; retries safe because the server is idempotent). After a claim: "Payment sent — waiting for staff to confirm" or the cash/card message; settled: paid message. Voided lines shown as "Removed by staff: {name} ×{qty}". Network failure: keep the entered reference and show "Couldn't reach the restaurant — tap again" (i18n). Polls `GET /api/guest/bill` every 10 s while open (30 s once paid, as today).
  - Staff Bills page: claim chip per row; confirm sheet shows table/pickup, the selected method's total and reference in large type, "Check your JazzCash / bank app for ref … and Rs … before confirming.", `amount_due_after_claim` warning in danger tokens, reused-reference warning with a checkbox "I've checked — confirm anyway" mapped to `acknowledge_reused_reference`; method pre-selected from the claim; "Confirm received" sends `expected_total`/`expected_method` from the selected method's preview; on 409 "Bill changed" replace the sheet's bill with the returned fresh bill and show "The bill changed — check the new total"; per-order device labels and a red "Joined late" chip; **Void** button per order with a reason prompt (`Sheet` with a short select: Wrong table / Guest changed mind / Duplicate / Other + text).
  - i18n keys `pay.*` (en/it/types).
- [ ] **Step 3: tests/lint/tsc both apps. Commit** `feat(web): pay from the table; staff confirm with expected totals, voids and device labels`.

# Slice 3 — Counter pickup

### Task 10: Schema for counter orders and pickup numbers

**Files:** Create `alembic/versions/0013_counter_pickup.py`. Modify `src/models/order.py`, `src/models/bill.py`, `src/models/restaurant.py`, seeds, `scripts/seed.py`, `src/schemas/owner.py` + settings route (add `pickup_prefix`).

- [ ] **Step 1: Failing tests**: order status `awaiting_payment` accepted; `collected_at` set while status is `placed` → IntegrityError (`chk_orders_collected`: `collected_at IS NULL OR status = 'bumped'`); duplicate (`restaurant_id`, `pickup_day`, `pickup_no`) → IntegrityError; `pickup_no` without `pickup_day` → IntegrityError; seed: each venue has exactly one `kind='counter'` table labelled "Counter" (Kehwa) / "Takeaway" (Angeethi) and `pickup_prefix` "K" / "P".
- [ ] **Step 2: Implement.** `orders`: status check adds `awaiting_payment`; `collected_at`, `collected_by` (FK users SET NULL). `bills`: `pickup_day` Date null, `pickup_no` Integer null, `UniqueConstraint("restaurant_id","pickup_day","pickup_no", name="uq_bills_pickup_no")`, check `(pickup_no IS NULL) = (pickup_day IS NULL)`. `restaurant.pickup_prefix` Text null (1–3 uppercase letters, validated in settings). Seeds: add `{"label": "Counter", "kind": "counter"}` / `{"label": "Takeaway", "kind": "counter"}` and `"pickup_prefix"`; seeder supports `kind`.
- [ ] **Step 3: Migration, green, drift. Commit** `feat(api): schema for counter pickup`.

### Task 11: Counter order lifecycle

**Files:** Create `src/services/counter.py`, `tests/test_counter.py`. Modify `src/routers/orders.py`, `src/services/bills.py` (settle releases), `src/routers/bills.py` (list `kind`, cancel, collect, uncollect), `src/routers/kitchen.py` (pickup label), `src/schemas/kitchen.py`, `src/services/analytics.py` (status filter), `src/routers/guest.py` (guest bill pickup fields).

- [ ] **Step 1: Failing tests**
  - Counter session order → order `awaiting_payment`, its own bill (`table_id` null, `bill_no` set, `pickup_day` = local date, `pickup_no` 1), guest bill `pickup_label == "K-001"`; a second counter order → its own bill, `K-002`; kitchen list excludes both; settle bill 1 (cash, expected total) → order `placed`, appears in kitchen with `pickup_label "K-001"`, `order_placed` published; bump → guest `order_status "bumped"`; `POST …/orders/{id}/collect` → `collected_at`, audit; collect again → 409; collect a `placed` order → 409; `uncollect` within 60 s → collected cleared; after backdating `collected_at` 61 s → 409.
  - Counter order cannot join another bill: a second order from the same counter session gets its own bill/number.
  - Day rollover: with `local_date` patched to the next day, numbering restarts at 1; the old uncollected order reports `pickup_yesterday: true` in the counter list.
  - Numbers never wrap: create bill with `pickup_no 999` then next → 1000, label `K-1000`.
  - Expiry: an unclaimed `awaiting_payment` order with `placed_at` 31 min ago is cancelled (bill `cancelled`, `cancel_reason "Expired unpaid"`) when `GET …/bills?kind=counter` is read; a claimed one is not; a settled one is never touched.
  - Cancel: `POST …/bills/{id}/cancel {"reason":"Guest left"}` on an unpaid counter bill → bill `cancelled`, order `cancelled`; on a claimed bill without reason → 422, with reason → 200 and audit notes the claim; on a settled bill → 409; on a table bill → 409.
  - Counter sessions: `POST /api/guest/service-calls` → 422 (already from Task 3).
  - Concurrency: 30 counter orders from 30 sessions in parallel → pickup numbers 1..30 exactly; expiry read racing a settle on the same bill ×20 → each bill ends either settled with order `placed`, or cancelled with order `cancelled`, never mixed.
  - Analytics: an `awaiting_payment` order is excluded from the brief revenue and menu engineering; after settle it is included.
- [ ] **Step 2: Implement.**
  - `services/counter.py`: `open_counter_bill(db, restaurant, table_id) -> Bill` under the same advisory lock key as `open_bill_for_table` (`bill:{restaurant_id}`): `bill_no = max+1`, `pickup_day = local_date(restaurant, clock_timestamp())`, `pickup_no = coalesce(max(pickup_no) for that day, 0) + 1`, `table_id=None`. `pickup_label(prefix, no) = f"{prefix or 'K'}-{no:03d}"` (≥1000 prints all digits). `expire_unpaid(db, restaurant)`: lock candidate bills `FOR UPDATE SKIP LOCKED` where counter (`pickup_no is not null`), `status='open'`, `claimed_at is null`, order `awaiting_payment` with `placed_at < now - 30 min`; set bill `cancelled` + reason, order `cancelled`.
  - `create_order`: if the session's table `kind == 'counter'` → `open_counter_bill`, order status `awaiting_payment`; publish nothing to the kitchen (only `bill_opened`).
  - `settle_bill`: after settling, `UPDATE orders SET status='placed' WHERE bill_id=:id AND status='awaiting_payment'`; router publishes `order_placed` for those order ids after commit.
  - Bills list: `kind=table|counter` filter (`pickup_no IS NULL` vs not); counter rows include `pickup_label`, `order_status`, `pickup_yesterday`; call `expire_unpaid` before listing counter bills and commit.
  - Kitchen: `KitchenOrderResponse.pickup_label: str | None` (from the order's bill).
  - Analytics `_SCOPE`: `o.status IN ('placed','bumped')` instead of `<> 'cancelled'` (and any other status filters in analytics/brief/forecast — grep for `cancelled`).
- [ ] **Step 3: green (concurrency tests 3×). Commit** `feat(api): counter pickup orders held until paid, with daily numbers, expiry and collection`.

### Task 12: Counter screens

**Files:** Modify the guest menu and order pages, guest i18n, owner Bills page (Tables / Counter tabs and queue), kitchen page, `apps/owner-web/src/lib/bill.ts` (+tests).

- [ ] **Step 1: Failing tests** in `bill.test.ts`: `counterColumn(row)` returns `awaiting | preparing | ready` from `status`/`order_status`/`collected`; `pickupText(row)` adds " · Yesterday" when flagged.
- [ ] **Step 2: Implement.**
  - Guest: counter sessions show the header "Counter order — pay first, then collect"; after ordering, a large pickup number card with the Pay sheet (Task 9) and the states "Paid — preparing your order", "Ready — collect K-042 at the counter" (large), "Collected · enjoy!"; no Call waiter.
  - Owner Bills page: tabs Tables / Counter; Counter tab has three columns (Awaiting payment with Confirm received / Cancel (reason prompt); Preparing; Ready with Collected and a 60 s Undo toast).
  - Kitchen: counter tickets show "PICKUP {pickup_label}" in large type in place of the table.
  - Owner Tables & QR page: the counter QR card ("Counter / Pickup" or "Takeaway / Parcel") printable like table QRs; payment details form (Task 6 API) and pickup prefix + extra call reason fields with server-side errors shown per field; "Sample — demo only" tag when `sample`.
- [ ] **Step 3: tests/lint/tsc. Commit** `feat(web): counter pickup for guests, staff and kitchen; venue payment settings`.

# Slice 4 — Pay-it-forward chai

### Task 13: Pay-it-forward ledger and handouts

**Files:** Create `src/models/pay_forward.py`, `alembic/versions/0014_pay_forward.py`, `src/services/pay_forward.py`, `tests/test_pay_forward.py`. Modify seeds (`pay_forward_chai` item, Rs 250 / cost 45, category "Drinks" at Angeethi and "Chai & Kehwa" at Kehwa, `sim_weight` 0), `src/services/bills.py` (settle writes `bought`), `src/routers/floor.py` (balance + give route), `src/models/order.py` (source adds `pay_forward`), `src/services/analytics.py`, `src/services/brief.py`, `src/schemas/owner.py`, guest bill response.

- [ ] **Step 1: Failing tests**
  - Settling a bill with 2 × pay-forward chai writes `pay_forward(kind="bought", quantity=2, order_id=…)`; balance 2; guest bill `pay_forward_count == 2`.
  - `POST …/pay-forward/give {"quantity":1}` → balance 1; creates an `Order(source="pay_forward", status="placed", total=0, bill_id=None)` with one line "Pay-it-forward chai" at `unit_price 0`, visible in the kitchen list with `pay_forward: true`; audit `pay_forward_given` actor `user:{id}`; balance 0 → 409 "None waiting"; quantity ≠ 1 → 422; another venue → 404.
  - Concurrency: balance 1, two parallel gives → one 200, one 409, balance 0, one handout order.
  - Analytics: handout orders never count in revenue, units or menu engineering (`source` filter); the brief has `pay_forward: {"bought": n, "given": m}` for the window; the chai sold counts as normal revenue once.
  - Voided pay-forward lines on a bill don't create `bought` rows.
- [ ] **Step 2: Implement.**
  - `pay_forward`: `id`, `restaurant_id` FK CASCADE, `kind` check (`bought`,`given`), `quantity` int check > 0, `order_id` FK `orders.id` SET NULL null, `user_id` FK users SET NULL null, `created_at`; index (`restaurant_id`, `created_at`).
  - `orders.source` check adds `pay_forward`; analytics `_SCOPE` adds `o.source IN ('live','simulated')`.
  - `give`: take `pg_advisory_xact_lock(hashtext('payforward:' || restaurant_id))`, compute balance, 409 if < 1, create a synthetic expired `GuestSession` (as the simulator does) and the handout order via `snapshot_order_item(item)` then set `unit_price=0`; insert `given` row; audit; commit; publish `pay_forward_given` and `order_placed`.
  - Settle: for each active order line whose menu item key is `pay_forward_chai` (look up the item id by `uuid5(SEED_ITEM_NAMESPACE, f"{slug}:pay_forward_chai")`; also accept any item flagged `pay_forward` if you add a boolean column — prefer a boolean `menu_item.is_pay_forward` added in this migration over key matching, set by the seeder), insert `bought` with the quantity.
  - Floor response gains `pay_forward_balance`.
- [ ] **Step 3: green (concurrency 3×), drift. Commit** `feat(api): pay-it-forward chai ledger and handouts`.

### Task 14: Pay-it-forward screens

**Files:** Modify Floor page, Bills counter tab (tile), kitchen page, guest order page, owner brief page, i18n.

- [ ] **Step 1: Failing tests** in `floor.test.ts`: `payForwardText(0) === "No chai waiting"`, `payForwardText(3) === "Pay-it-forward chai: 3 waiting"`.
- [ ] **Step 2: Implement.** Floor page tile with "Give one" (disabled at 0, shows 409 message); same tile on the Bills Counter tab; kitchen ticket header "PAY-IT-FORWARD · Chai" for `pay_forward` orders; guest paid state adds "You bought N chai for someone who needs it. Shukriya." when `pay_forward_count > 0`; brief page small card "Pay-it-forward: N bought · M given this week" (not part of revenue tiles). Menu shows the item with the description "A chai for someone who needs it — we hand it out free, no questions asked."
- [ ] **Step 3: tests/lint/tsc. Commit** `feat(web): pay-it-forward chai on floor, kitchen, guest and brief`.

# Final

### Task 15: Browser stories, docs, client, full verification

**Files:** Modify `e2e/flows.spec.ts` (or add `e2e/self-service.spec.ts`), `scripts/verify_phase1.sh`, `README.md`, `docs/architecture.md`, `docs/analytics.md`, `CLAUDE.md`, `packages/api-client` (regenerate).

- [ ] **Step 1: Browser stories** — implement the nine stories in spec §6.6 exactly, as one or more serial `describe` blocks with clean-up in `beforeAll` (bump tickets, settle/cancel open bills, resolve calls, clear tables, reset pay-forward via settling a bill if needed). Story 9 uses `page.route` or CDP network throttling (`await context.newCDPSession(page)` → `Network.emulateNetworkConditions` slow-3G) at viewport 360×780 and a forced offline toggle around "I've paid". Backdating for stories 5–6 uses demo-only API calls? **No** — add no test-only endpoints; backdate via `docker compose exec -T postgres psql …` from a small helper script in `e2e/helpers.ts` (connection args from the compose defaults, never from `.env`), or seed through the API and wait. Prefer the psql helper.
- [ ] **Step 2: `verify_phase1.sh`**: the live-order step also exercises a counter order (unpaid → not in kitchen → settle with expected total → in kitchen) and a pay-forward give; brief step asserts `pay_forward` present; floor endpoint returns tiles for both venues.
- [ ] **Step 3: Docs.** README: table self-service, Call waiter, Floor view (states and thresholds with the research link), pay-from-table with staff confirmation and the explicit "the demo cannot verify a transaction with a bank" statement, counter pickup, pay-it-forward, owner payment settings and validation. `docs/architecture.md`: new tables/columns, events, safeguards list. `docs/analytics.md`: status/source filters, pay-forward excluded from revenue. `CLAUDE.md` Architecture adds: "Guests never settle bills; every settle carries the expected total and method and is refused on mismatch."
- [ ] **Step 4: Regenerate the API client** (stack up: `LLM_PROVIDER=mock DEMO_MODE=true make up && make migrate && make seed && make gen-client`).
- [ ] **Step 5: `LLM_PROVIDER=mock DEMO_MODE=true make verify-f`** → all steps PASS; `make ci` green; branding clean. Fix root causes of any failure (separate commits for real bugs).
- [ ] **Step 6: Commit** `test: real-world self-service stories; docs for floor, payments, counter and pay-it-forward`.

---

## Self-review notes

- Spec coverage: §1 guest flows (T4, T7, T9, T12, T14), §2 staff screens (T4, T9, T12, T14), §3 data model/API (T1, T3, T5–T8, T10–T13), §4 safeguards 1–12 (T7 claim total + privacy, T8 expected total/reused ref/accountability/void/device labels, T6 validation, T11 expiry/collect undo/pickup numbers, T13 balance), §5 errors (tests in T3, T7, T8, T11, T13), §6 testing (each task + T8 money agreement + T15 stories), §7 statement (T9 copy, T15 README).
- Fixed while planning: Seated must reset after a settle as well as a clear (`reset = max(cleared_at, last_settled_at)`), otherwise a paid table would show "Seated" instead of "Needs clearing". Analytics must include only `placed`/`bumped` live/simulated orders, otherwise unpaid counter orders and handouts would count as revenue. Bills checks must be rewritten to allow `cancelled`.
- Known follow-ups: counter history in the simulator and channel margins; "Now serving" screen; sound alerts; server sections.
