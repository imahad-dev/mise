# Safer Table Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop remote fake table orders by requiring staff to open a table before it can order
and approve its first order, make the Floor view show the new waiting moments, and add a daily
service report — all built on facts the system already records, no cameras.

**Architecture:** One new row, `table_sitting`, is the source of truth for "is this table open
right now" and "has its first order been approved". Everything else (the Floor view, the guest
order endpoint, the daily report) reads or writes through it. Idle sittings are closed lazily —
the next request that touches the table closes it if it's gone stale — following the same
pattern the codebase already uses for expired counter bills (`is_expired_unpaid` /
`revive_expired` in `services/bills.py`), so no new scheduler or background-job infrastructure
is introduced.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0, Alembic, Postgres, Redis (fixed-window limits,
same as `request_limits.py`); Next.js 15 (`apps/owner-web`, `apps/guest-web`); Vitest; Playwright.

**Scope note on `sitting_code_required` default:** the spec says the two *overseas* venues
default to requiring a code. Those venues don't exist yet (they're created in a later
sub-project's spec). This migration adds the column with `server_default=false` for every
existing venue (both current local venues); the overseas venues' own creation work sets it to
`true` for themselves. This is not a contradiction of the spec — it's the column existing ahead
of the rows that will use `true`.

---

## Task 1: Migration — `table_sitting`, order status, new columns

**Files:**
- Create: `services/api/alembic/versions/0017_safer_table_ordering.py`
- Test: `services/api/tests/test_migrations.py` (if it exists — check; otherwise this task's
  verification is step 3 below, running the migration against the dev DB)

- [ ] **Step 1: Check whether a migration smoke test exists**

Run: `grep -rl "def test_" services/api/tests/test_migrations.py 2>/dev/null || echo "no such file"`

If it exists, read it to follow its pattern for the new migration. If not (expected — no other
migration in this repo has a dedicated test file), skip straight to Step 2.

- [ ] **Step 2: Write the migration**

```python
"""Table sittings: staff-opened tables, first-order approval, optional per-sitting code.

Revision ID: 0017_safer_table_ordering
Revises: 0016_pay_forward_hardening
Create Date: 2026-10-31 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_safer_table_ordering"
down_revision: str | None = "0016_pay_forward_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "table_sitting",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dining_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "opened_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("code_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('settled', 'cancelled', 'staff_closed', 'idle_timeout')",
            name="chk_table_sitting_close_reason",
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (close_reason IS NULL)",
            name="chk_table_sitting_closed_pair",
        ),
        sa.CheckConstraint("code IS NULL OR code ~ '^[0-9]{4}$'", name="chk_table_sitting_code"),
    )
    op.create_index("idx_table_sitting_table_id", "table_sitting", ["table_id"])
    op.create_index(
        "uq_table_sitting_open_per_table",
        "table_sitting",
        ["table_id"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )

    op.add_column(
        "restaurant",
        sa.Column(
            "sitting_code_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "restaurant",
        sa.Column(
            "first_order_cap_multiplier",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("4"),
        ),
    )

    op.add_column(
        "orders",
        sa.Column(
            "sitting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("table_sitting.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_orders_sitting_id", "orders", ["sitting_id"])
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status",
        "orders",
        "status IN ('awaiting_payment', 'pending_approval', 'placed', 'bumped', 'cancelled')",
    )

    op.add_column(
        "guest_session",
        sa.Column(
            "sitting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("table_sitting.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_guest_session_sitting_id", "guest_session", ["sitting_id"])


def downgrade() -> None:
    op.drop_index("idx_guest_session_sitting_id", table_name="guest_session")
    op.drop_column("guest_session", "sitting_id")
    op.drop_constraint("chk_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "chk_orders_status",
        "orders",
        "status IN ('awaiting_payment', 'placed', 'bumped', 'cancelled')",
    )
    op.drop_index("idx_orders_sitting_id", table_name="orders")
    op.drop_column("orders", "sitting_id")
    op.drop_column("restaurant", "first_order_cap_multiplier")
    op.drop_column("restaurant", "sitting_code_required")
    op.drop_index("uq_table_sitting_open_per_table", table_name="table_sitting")
    op.drop_index("idx_table_sitting_table_id", table_name="table_sitting")
    op.drop_table("table_sitting")
```

- [ ] **Step 3: Run the migration against the dev database and verify it applies cleanly**

Run (from `services/api`, inside the API container — follow the project's existing `make`
target for this, e.g. `make reset` then `make up` with `LLM_PROVIDER=mock DEMO_MODE=true`):

```bash
LLM_PROVIDER=mock DEMO_MODE=true make reset
```

Expected: migration `0017_safer_table_ordering` applies with no errors, and
`alembic current` (run the same way the project already runs alembic commands inside the
container) reports `0017_safer_table_ordering (head)`.

- [ ] **Step 4: Commit**

```bash
git add services/api/alembic/versions/0017_safer_table_ordering.py
git commit -m "feat(api): migration for table sittings, approval status, sitting columns

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: `TableSitting` model and column additions

**Files:**
- Create: `services/api/src/models/sitting.py`
- Modify: `services/api/src/models/restaurant.py` (add two columns)
- Modify: `services/api/src/models/order.py` (add `sitting_id` + relationship)
- Modify: `services/api/src/models/session.py` (add `sitting_id` + relationship)
- Modify: `services/api/src/models/__init__.py` (register `TableSitting`)
- Modify: `services/api/src/models/dining_table.py` (add `sittings` relationship, for
  completeness and symmetry with `restaurant`/`tables`)

- [ ] **Step 1: Write the model**

```python
"""Table sitting: one party's visit to one table, from staff open to close."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class TableSitting(Base):
    __tablename__ = "table_sitting"
    __table_args__ = (
        CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('settled', 'cancelled', 'staff_closed', 'idle_timeout')",
            name="chk_table_sitting_close_reason",
        ),
        CheckConstraint(
            "(closed_at IS NULL) = (close_reason IS NULL)",
            name="chk_table_sitting_closed_pair",
        ),
        CheckConstraint("code IS NULL OR code ~ '^[0-9]{4}$'", name="chk_table_sitting_code"),
        Index("idx_table_sitting_table_id", "table_id"),
        Index(
            "uq_table_sitting_open_per_table",
            "table_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dining_table.id", ondelete="CASCADE"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_required: Mapped[bool] = mapped_column(
        "code_required", Text, nullable=False, server_default=text("false")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    table: Mapped["DiningTable"] = relationship("DiningTable", lazy="raise")  # noqa: F821
```

Fix the `code_required` column type — it must be `Boolean`, not `Text` (copy error above
corrected here):

```python
    code_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
```

Add `Boolean` to the `sqlalchemy` import line at the top of the file.

- [ ] **Step 2: Add the two columns to `Restaurant`**

In `services/api/src/models/restaurant.py`, add to the `sqlalchemy` import line: `Numeric`.
After the existing `pickup_prefix` column (around line 35), add:

```python
    sitting_code_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    first_order_cap_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("4")
    )
```

Add `from decimal import Decimal` to the imports if not already present (check first —
`restaurant.py` currently has no `Decimal` import).

- [ ] **Step 3: Add `sitting_id` to `Order`**

In `services/api/src/models/order.py`, after the existing `bill_id` column, add:

```python
    sitting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sitting.id", ondelete="SET NULL"),
        nullable=True,
    )
```

And add `Index("idx_orders_sitting_id", "sitting_id"),` to `Order.__table_args__`. Add a
relationship next to the existing `table` relationship:

```python
    sitting: Mapped["TableSitting | None"] = relationship("TableSitting", lazy="raise")  # noqa: F821
```

- [ ] **Step 4: Add `sitting_id` to `GuestSession`**

In `services/api/src/models/session.py`, after the existing `table_id` column, add:

```python
    sitting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("table_sitting.id", ondelete="SET NULL"),
        nullable=True,
    )
```

Add `Index("idx_guest_session_sitting_id", "sitting_id"),` to `GuestSession.__table_args__`,
and a relationship next to the existing `table` relationship:

```python
    sitting: Mapped["TableSitting | None"] = relationship("TableSitting", lazy="raise")  # noqa: F821
```

- [ ] **Step 5: Register the model**

In `services/api/src/models/__init__.py`, add `from src.models.sitting import TableSitting` and
add `"TableSitting"` to `__all__` (keep both lists alphabetically sorted, matching the existing
order).

- [ ] **Step 6: Verify the models import cleanly and match the migration**

Run (inside the API container, same way other API checks run in this repo):

```bash
python -c "from src.models import TableSitting; print(TableSitting.__table__.columns.keys())"
```

Expected: prints the column list with no import error. Then run
`alembic check` (or the project's equivalent autogenerate-diff check, if `make ci` runs one) to
confirm the models match migration `0017` exactly — no drift.

- [ ] **Step 7: Commit**

```bash
git add services/api/src/models/sitting.py services/api/src/models/restaurant.py \
  services/api/src/models/order.py services/api/src/models/session.py \
  services/api/src/models/dining_table.py services/api/src/models/__init__.py
git commit -m "feat(api): TableSitting model and sitting columns on restaurant/order/session

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(If no change to `dining_table.py` ended up being needed because nothing reads a `sittings`
back-reference yet, drop it from the `git add` list — don't add an unused relationship.)

---

## Task 3: `services/sitting.py` — pure state + DB helpers

This mirrors the split in `services/floor.py` (pure facts → pure state) and `services/bills.py`
(`is_expired_unpaid` pure predicate + DB functions that act on it).

**Files:**
- Create: `services/api/src/services/sitting.py`
- Test: `services/api/tests/test_sitting.py`

- [ ] **Step 1: Write the failing tests for the pure functions**

```python
"""Tests for services/sitting.py: pure idle/code logic, no DB."""

from datetime import datetime, timedelta, timezone

from src.services.sitting import IDLE_TIMEOUT, generate_code, is_idle

NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_not_idle_just_opened():
    assert is_idle(opened_at=NOW, last_activity_at=None, now=NOW) is False


def test_idle_after_90_minutes_of_silence():
    opened = NOW - timedelta(minutes=95)
    assert is_idle(opened_at=opened, last_activity_at=None, now=NOW) is True


def test_not_idle_with_recent_activity_even_if_opened_long_ago():
    opened = NOW - timedelta(hours=3)
    recent = NOW - timedelta(minutes=10)
    assert is_idle(opened_at=opened, last_activity_at=recent, now=NOW) is False


def test_idle_timeout_is_90_minutes():
    assert IDLE_TIMEOUT == timedelta(minutes=90)


def test_generate_code_is_four_digits():
    code = generate_code()
    assert len(code) == 4
    assert code.isdigit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest services/api/tests/test_sitting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.sitting'`

- [ ] **Step 3: Write the pure functions**

```python
"""Table sittings: pure idle check and code generation, and the DB operations around them."""

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order import Order
from src.models.service_call import ServiceCall
from src.models.sitting import TableSitting

IDLE_TIMEOUT = timedelta(minutes=90)


def is_idle(*, opened_at: datetime, last_activity_at: datetime | None, now: datetime) -> bool:
    """No order, call or payment activity for IDLE_TIMEOUT since the sitting opened."""
    since = last_activity_at or opened_at
    return now - since >= IDLE_TIMEOUT


def generate_code() -> str:
    """A random 4-digit code, read aloud by staff — not cryptographic, just hard to guess."""
    return f"{secrets.randbelow(10000):04d}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest services/api/tests/test_sitting.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: Add the DB helpers (no new tests here — covered by the router/integration tests
  in Tasks 6 and 8, following this codebase's existing pattern where DB-touching service
  functions are tested through their router)**

Append to `services/sitting.py`:

```python
async def open_sitting_for_table(
    db: AsyncSession, table_id: uuid.UUID, user_id: uuid.UUID, code_required: bool
) -> TableSitting:
    """Open a table, caller commits. Raises IntegrityError if one is already open (caller
    should have checked the Floor tile shows `free`, so this is a race guard)."""
    sitting = TableSitting(
        table_id=table_id,
        opened_by_user_id=user_id,
        code_required=code_required,
        code=generate_code() if code_required else None,
    )
    db.add(sitting)
    await db.flush()
    return sitting


async def get_open_sitting(db: AsyncSession, table_id: uuid.UUID) -> TableSitting | None:
    """The table's open sitting, lazily closing it first if it has gone idle."""
    sitting = (
        await db.execute(
            select(TableSitting)
            .where(TableSitting.table_id == table_id, TableSitting.closed_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sitting is None:
        return None
    now = await db.scalar(select(func.clock_timestamp()))
    last_activity = await _last_activity(db, sitting.id)
    if is_idle(opened_at=sitting.opened_at, last_activity_at=last_activity, now=now):
        sitting.closed_at = now
        sitting.close_reason = "idle_timeout"
        await db.flush()
        return None
    return sitting


async def _last_activity(db: AsyncSession, sitting_id: uuid.UUID) -> datetime | None:
    order_activity = await db.scalar(
        select(func.max(Order.placed_at)).where(Order.sitting_id == sitting_id)
    )
    call_activity = await db.scalar(
        select(func.max(ServiceCall.created_at)).where(
            ServiceCall.table_id == select(TableSitting.table_id)
            .where(TableSitting.id == sitting_id)
            .scalar_subquery()
        )
    )
    candidates = [t for t in (order_activity, call_activity) if t is not None]
    return max(candidates) if candidates else None


async def close_sitting_for_table(
    db: AsyncSession, table_id: uuid.UUID, reason: str, now: datetime
) -> None:
    """Close the table's open sitting, if any. No-op for counter tables (never have one) and
    for a table with no open sitting (settle/void paths call this unconditionally — it's a
    no-op, not an error, when there's nothing to close)."""
    sitting = (
        await db.execute(
            select(TableSitting)
            .where(TableSitting.table_id == table_id, TableSitting.closed_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sitting is None:
        return
    sitting.closed_at = now
    sitting.close_reason = reason
```

- [ ] **Step 6: Commit**

```bash
git add services/api/src/services/sitting.py services/api/tests/test_sitting.py
git commit -m "feat(api): sitting idle check, code generation, and DB helpers

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Session-scoped rate limit helper

**Files:**
- Modify: `services/api/src/request_limits.py`
- Test: `services/api/tests/test_request_limits.py` (check if it exists first)

- [ ] **Step 1: Check for an existing test file**

Run: `ls services/api/tests/test_request_limits.py 2>/dev/null || echo "none"`

If one exists, add the new test to it following its existing fixture pattern (likely a fake/real
Redis fixture — read the file first). If none exists, create it fresh, modelling it on how
`enforce_ip_limit` would be tested (check `tests/test_orders.py` or similar for how Redis is
exercised in this test suite, since IP limiting is presumably tested there already).

- [ ] **Step 2: Write the failing test**

```python
"""Tests for the session-scoped Redis rate limit."""

import pytest
from fastapi import HTTPException

from src.request_limits import enforce_session_limit


@pytest.mark.asyncio
async def test_allows_up_to_the_limit_then_blocks(redis_client_for_tests):
    session_id = "11111111-1111-1111-1111-111111111111"
    for _ in range(3):
        await enforce_session_limit(session_id, "test_scope", limit=3, window_s=300, detail="Too many")
    with pytest.raises(HTTPException) as exc:
        await enforce_session_limit(session_id, "test_scope", limit=3, window_s=300, detail="Too many")
    assert exc.value.status_code == 429
```

(Use whatever Redis test fixture name this repo's existing tests already use — grep
`tests/conftest.py` for a Redis fixture and substitute its real name for
`redis_client_for_tests` above before running.)

- [ ] **Step 3: Run to verify it fails**

Run: `pytest services/api/tests/test_request_limits.py -v`
Expected: FAIL — `ImportError: cannot import name 'enforce_session_limit'`

- [ ] **Step 4: Add the function**

In `services/api/src/request_limits.py`, after `enforce_ip_limit`, add a shared implementation
and have both call it (keeps one fixed-window algorithm in one place):

```python
async def _enforce_fixed_window(
    key: str, limit: int, window_s: int, detail: str
) -> None:
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_s)
        if count > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Redis error checking rate limit for %s: %s", key, e)


async def enforce_session_limit(
    session_id: str, scope: str, limit: int, window_s: int, detail: str
) -> None:
    """Allow `limit` requests per `window_s` seconds per guest session; 429 beyond that."""
    await _enforce_fixed_window(f"rate_limit:{scope}:{session_id}", limit, window_s, detail)
```

Then simplify `enforce_ip_limit` to call the shared helper too (refactor, behaviour unchanged):

```python
async def enforce_ip_limit(
    request: Request, scope: str, limit: int, window_s: int, detail: str
) -> None:
    """Allow `limit` requests per `window_s` seconds per client IP; 429 beyond that."""
    await _enforce_fixed_window(f"rate_limit:{scope}:{client_ip(request)}", limit, window_s, detail)
```

- [ ] **Step 5: Run to verify it passes, and re-run the existing IP-limit tests**

Run: `pytest services/api/tests/test_request_limits.py -v` and whatever existing test file
exercises `enforce_ip_limit` today (grep for it: `grep -rl enforce_ip_limit services/api/tests`).
Expected: all PASS — the refactor must not change `enforce_ip_limit`'s behaviour.

- [ ] **Step 6: Commit**

```bash
git add services/api/src/request_limits.py services/api/tests/test_request_limits.py
git commit -m "refactor(api): share one fixed-window limiter, add a session-scoped variant

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: `services/floor.py` — new states and alert thresholds

**Files:**
- Modify: `services/api/src/services/floor.py`
- Modify: `services/api/tests/test_floor.py` (or wherever its Python unit tests live — check
  first: `find services/api/tests -iname "*floor*"`)

- [ ] **Step 1: Read the existing test file to match its style**

Run: `find services/api/tests -iname "*floor*"` and read whatever it finds before writing new
tests, so new tests use the same `TableFacts(...)` construction style as the existing ones.

- [ ] **Step 2: Write the failing tests**

Add to the existing floor test file (same file, not a new one — these are more cases of the same
`table_state` function):

```python
def test_guests_waiting_badge_before_table_opened():
    now = datetime(2026, 10, 31, 12, 3, 0, tzinfo=timezone.utc)
    f = TableFacts(
        table_id="t1", label="T1", kind="table", cleared_at=None,
        last_session_at=datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc),
        open_bill=False, paying_since=None, oldest_placed_at=None, has_active_orders=False,
        last_settled_at=None, last_cancelled_at=None, call_reason=None, call_since=None,
        running_total=None, sitting_open=False, approval_pending=None,
    )
    result = table_state(f, now)
    assert result.state == "seated"
    assert result.waiting_for_open is True
    assert result.level == "amber"  # 3 minutes: amber at 1, red at 3


def test_approval_needed_takes_priority_and_times_from_pending_order():
    now = datetime(2026, 10, 31, 12, 2, 30, tzinfo=timezone.utc)
    f = TableFacts(
        table_id="t1", label="T1", kind="table", cleared_at=None,
        last_session_at=datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc),
        open_bill=True, paying_since=None, oldest_placed_at=None, has_active_orders=False,
        last_settled_at=None, last_cancelled_at=None, call_reason=None, call_since=None,
        running_total=None, sitting_open=True,
        approval_pending=datetime(2026, 10, 31, 12, 0, 30, tzinfo=timezone.utc),
    )
    result = table_state(f, now)
    assert result.state == "approval_needed"
    assert result.level == "red"  # 2 minutes: amber at 1, red at 2


def test_seated_timer_starts_from_sitting_open_not_guest_session():
    now = datetime(2026, 10, 31, 12, 6, 0, tzinfo=timezone.utc)
    f = TableFacts(
        table_id="t1", label="T1", kind="table", cleared_at=None,
        last_session_at=datetime(2026, 10, 31, 11, 0, 0, tzinfo=timezone.utc),  # long ago
        open_bill=True, paying_since=None, oldest_placed_at=None, has_active_orders=False,
        last_settled_at=None, last_cancelled_at=None, call_reason=None, call_since=None,
        running_total=None, sitting_open=True, sitting_opened_at=datetime(
            2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc
        ), approval_pending=None,
    )
    result = table_state(f, now)
    assert result.state == "seated"
    assert result.since == datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    assert result.level == "red"  # 6 minutes since sitting opened
```

- [ ] **Step 3: Run to verify they fail**

Run: `pytest services/api/tests/test_floor.py -v -k "guests_waiting or approval_needed or seated_timer"`
Expected: FAIL — `TableFacts` has no field `sitting_open` etc.

- [ ] **Step 4: Extend `TableFacts`, `TileState`, `THRESHOLDS`, and `table_state`**

In `services/api/src/services/floor.py`:

```python
State = Literal[
    "free", "seated", "ordered", "served", "paying", "needs_clearing", "called",
    "approval_needed",
]
```

Add to `THRESHOLDS`:

```python
THRESHOLDS: dict[str, tuple[timedelta, timedelta]] = {
    "seated": (3 * MIN, 5 * MIN),
    "ordered": (12 * MIN, 18 * MIN),
    "paying": (3 * MIN, 5 * MIN),
    "needs_clearing": (2 * MIN, 5 * MIN),
    "approval_needed": (1 * MIN, 2 * MIN),
    "guests_waiting": (1 * MIN, 3 * MIN),
}
```

Add fields to `TableFacts` (new, all with defaults so every existing call site — the router,
the existing tests — still works unmodified):

```python
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
    last_cancelled_at: datetime | None
    call_reason: str | None
    call_since: datetime | None
    running_total: Decimal | None
    sitting_open: bool = False
    sitting_opened_at: datetime | None = None
    approval_pending: datetime | None = None  # placed_at of the sitting's unapproved first order
```

Add a field to `TileState`:

```python
@dataclass(frozen=True)
class TileState:
    state: State
    since: datetime | None
    level: Level
    reason: str | None = None
    waiting_for_open: bool = False  # guests have scanned but no sitting is open yet
```

Insert new branches at the top of `table_state`, before the existing `call_reason` check (highest
priority, since an unapproved order blocks the kitchen):

```python
def table_state(f: TableFacts, now: datetime) -> TileState | None:
    if f.kind != "table":
        return None
    if f.approval_pending is not None:
        return TileState(
            "approval_needed", f.approval_pending, _level("approval_needed", f.approval_pending, now)
        )
    if f.call_reason is not None:
        return TileState("called", f.call_since, "red", f.call_reason)
    if not f.sitting_open and f.last_session_at is not None and not _after(
        max((t for t in (f.last_settled_at, f.last_cancelled_at, f.cleared_at) if t is not None), default=None),
        f.last_session_at,
    ):
        # A guest has scanned (or ordering is otherwise expected) but staff haven't opened the
        # table yet, and nothing has reset that scan since.
        return TileState(
            "seated", f.last_session_at, _level("guests_waiting", f.last_session_at, now),
            waiting_for_open=True,
        )
    if f.open_bill:
        if f.paying_since is not None:
            return TileState("paying", f.paying_since, _level("paying", f.paying_since, now))
        seated_since = f.sitting_opened_at or f.oldest_placed_at or f.last_session_at
        if f.oldest_placed_at is not None:
            return TileState(
                "ordered", f.oldest_placed_at, _level("ordered", f.oldest_placed_at, now)
            )
        if f.has_active_orders:
            return TileState("served", None, "none")
    ended = max(
        (t for t in (f.last_settled_at, f.last_cancelled_at) if t is not None), default=None
    )
    reset = max((t for t in (f.cleared_at, ended) if t is not None), default=None)
    if f.open_bill or _after(f.last_session_at, reset):
        seated_since = f.sitting_opened_at if f.sitting_open else f.last_session_at
        return TileState("seated", seated_since, _level("seated", seated_since, now))
    if _after(ended, f.cleared_at):
        return TileState("needs_clearing", ended, _level("needs_clearing", ended, now))
    return TileState("free", None, "none")
```

This duplicates `oldest_placed_at`'s "ordered" check — tidy that up: the `seated_since` line added
right before the `f.oldest_placed_at` check is dead code there (the `"ordered"` branch doesn't use
it). Move it down into the actual `"seated"` branch only, where it's used. Remove the unused
`seated_since` line above the `oldest_placed_at` check.

- [ ] **Step 5: Run to verify all floor tests pass, including the pre-existing ones**

Run: `pytest services/api/tests/test_floor.py -v`
Expected: all PASS — the three new tests, and every test that existed before this task
(`TableFacts`'s new fields all default, so old call sites are unaffected).

- [ ] **Step 6: Commit**

```bash
git add services/api/src/services/floor.py services/api/tests/test_floor.py
git commit -m "feat(api): approval_needed Floor state and a guests-waiting-to-order badge

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Floor router — open/close table, approve/decline, show code

**Files:**
- Modify: `services/api/src/routers/floor.py`
- Modify: `services/api/src/schemas/floor.py`
- Modify: `services/api/src/routers/orders.py` (approve/decline act on `Order`, so they live
  next to `create_order` — see Task 7; this task adds open/close only)
- Test: `services/api/tests/test_floor.py` (router-level tests, likely a second test file or a
  separate class — check existing conventions with
  `grep -rl "async def test_.*floor" services/api/tests`)

- [ ] **Step 1: Write the schemas**

Add to `services/api/src/schemas/floor.py`:

```python
class OpenSittingResponse(BaseModel):
    sitting_id: uuid.UUID
    code: str | None  # shown to staff once, to read aloud; never sent to any guest endpoint
    opened_at: datetime


class CloseSittingResponse(BaseModel):
    table_id: uuid.UUID
    closed_at: datetime
```

Extend `FloorTile` with the fields the new states need:

```python
class FloorTile(BaseModel):
    table_id: uuid.UUID
    label: str
    state: str
    level: str
    since: datetime | None
    reason: str | None
    reason_label: str | None
    running_total: Decimal | None
    bill_id: uuid.UUID | None
    call_id: uuid.UUID | None
    sitting_open: bool
    waiting_for_open: bool
    pending_order_id: uuid.UUID | None  # set when state == "approval_needed"
    pending_order_total: Decimal | None
    pending_order_items: int | None
```

- [ ] **Step 2: Write the failing router tests**

Follow the existing style in whichever file already tests `floor.py`'s router (e.g. opening a
table, asserting 201/409, reading back the Floor tile). At minimum:

```python
async def test_open_table_creates_sitting_and_returns_code_when_required(client, owner_token, table):
    resp = await client.post(
        f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table.id}/sitting",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] is None or len(body["code"]) == 4


async def test_open_table_twice_conflicts(client, owner_token, table):
    await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table.id}/sitting", headers=auth_headers(owner_token))
    resp = await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table.id}/sitting", headers=auth_headers(owner_token))
    assert resp.status_code == 409


async def test_close_table_with_open_bill_is_refused(client, owner_token, table_with_open_bill):
    resp = await client.delete(
        f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table_with_open_bill.id}/sitting",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 409
    assert "Settle the bill first" in resp.json()["detail"]


async def test_close_table_without_a_bill_succeeds(client, owner_token, table):
    await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table.id}/sitting", headers=auth_headers(owner_token))
    resp = await client.delete(
        f"/api/restaurants/{RESTAURANT_SLUG}/tables/{table.id}/sitting",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200
```

(Adapt fixture names — `client`, `owner_token`, `table`, `table_with_open_bill`,
`auth_headers` — to whatever this test suite's `conftest.py` actually provides; read it first.)

- [ ] **Step 3: Run to verify they fail**

Run: `pytest services/api/tests/test_floor.py -v -k "open_table or close_table"`
Expected: FAIL — 404, the routes don't exist yet.

- [ ] **Step 4: Add the routes**

In `services/api/src/routers/floor.py`, add imports for `TableSitting`,
`close_sitting_for_table`, `get_open_sitting`, `open_sitting_for_table`, `Order`, then:

```python
@router.post(
    "/tables/{table_id}/sitting",
    response_model=OpenSittingResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**RESPONSES, 409: {"description": "A sitting is already open for this table"}},
)
async def open_table(
    table_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> OpenSittingResponse:
    rid = access.restaurant.id
    table = (
        await db.execute(
            select(DiningTable).where(DiningTable.id == table_id, DiningTable.restaurant_id == rid)
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    existing = await get_open_sitting(db, table.id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Table is already open")
    sitting = await open_sitting_for_table(
        db, table.id, access.user.id, access.restaurant.sitting_code_required
    )
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_opened",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id), "sitting_id": str(sitting.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_opened", "table_id": str(table.id)})
    )
    return OpenSittingResponse(sitting_id=sitting.id, code=sitting.code, opened_at=sitting.opened_at)


@router.delete(
    "/tables/{table_id}/sitting",
    response_model=CloseSittingResponse,
    responses={
        **RESPONSES,
        409: {"description": "Settle the bill first, or no sitting is open"},
    },
)
async def close_table(
    table_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> CloseSittingResponse:
    rid = access.restaurant.id
    table = (
        await db.execute(
            select(DiningTable).where(DiningTable.id == table_id, DiningTable.restaurant_id == rid)
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    open_bill = await db.scalar(
        select(Bill.id).where(Bill.table_id == table.id, Bill.status == "open").limit(1)
    )
    if open_bill is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Settle the bill first")
    sitting = await get_open_sitting(db, table.id)
    if sitting is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No sitting is open")
    now = await db.scalar(select(func.clock_timestamp()))
    await close_sitting_for_table(db, table.id, "staff_closed", now)
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_closed",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_closed", "table_id": str(table.id)})
    )
    return CloseSittingResponse(table_id=table.id, closed_at=now)
```

- [ ] **Step 5: Wire the new Floor-tile fields into `get_floor`**

In `get_floor`, after loading `calls`, load open sittings and pending-approval orders for the
restaurant's tables in two more batched queries (same style as the existing `last_session`,
`open_bills` dicts):

```python
    sittings = {
        s.table_id: s
        for s in (
            await db.scalars(
                select(TableSitting).where(
                    TableSitting.table_id.in_([t.id for t in tables]),
                    TableSitting.closed_at.is_(None),
                )
            )
        ).all()
    }
    pending = {
        o.table_id: o
        for o in (
            await db.scalars(
                select(Order).where(
                    Order.restaurant_id == rid, Order.status == "pending_approval"
                )
            )
        ).all()
    }
```

Then, inside the `for t in tables:` loop, pass the new facts and read back the new tile fields:

```python
        sitting = sittings.get(t.id)
        pend = pending.get(t.id)
        tile = table_state(
            TableFacts(
                table_id=str(t.id),
                label=t.label,
                kind=t.kind,
                cleared_at=t.cleared_at,
                last_session_at=last_session.get(t.id),
                open_bill=bill is not None,
                paying_since=bill.bill_requested_at if bill else None,
                oldest_placed_at=bill.oldest if bill else None,
                has_active_orders=bool(bill and bill.active),
                last_settled_at=last_settled.get(t.id),
                last_cancelled_at=last_cancelled.get(t.id),
                call_reason=call.reason if call else None,
                call_since=call.created_at if call else None,
                running_total=total,
                sitting_open=sitting is not None,
                sitting_opened_at=sitting.opened_at if sitting else None,
                approval_pending=pend.placed_at if pend else None,
            ),
            now,
        )
        if tile is None:
            continue
        tiles.append(
            FloorTile(
                table_id=t.id,
                label=t.label,
                state=tile.state,
                level=tile.level,
                since=tile.since,
                reason=tile.reason,
                reason_label=reason_label(tile.reason, extra),
                running_total=total,
                bill_id=bill.id if bill else None,
                call_id=call.id if call else None,
                sitting_open=sitting is not None,
                waiting_for_open=tile.waiting_for_open,
                pending_order_id=pend.id if pend else None,
                pending_order_total=pend.total if pend else None,
                pending_order_items=len(pend.items) if pend else None,
            )
        )
```

`pend.items` needs eager loading — add `.options(selectinload(Order.items))` to the `pending`
query's `select(Order)` and import `selectinload` from `sqlalchemy.orm` (check the file's
existing imports first — it may already import it for another query; if not, add it).

- [ ] **Step 6: Run to verify all floor router tests pass**

Run: `pytest services/api/tests/test_floor.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src/routers/floor.py services/api/src/schemas/floor.py \
  services/api/tests/test_floor.py
git commit -m "feat(api): open/close table endpoints and sitting/approval fields on Floor tiles

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Orders router — pending approval, approve/decline, limits

**Files:**
- Modify: `services/api/src/routers/orders.py`
- Modify: `services/api/src/schemas/orders.py`
- Test: `services/api/tests/test_orders.py`

- [ ] **Step 1: Extend the schemas**

In `services/api/src/schemas/orders.py`:

```python
class CreateOrderRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)
    items: list[OrderItemRequest] = Field(..., min_length=1, max_length=50)
    acknowledge_allergen_risk: bool = False
    code: str | None = Field(default=None, min_length=4, max_length=4)
```

Add a validator enforcing the 30-item quantity cap (total across lines, not line count — a
guest ordering many different single dishes shouldn't be blocked, but 30 portions should be):

```python
    @model_validator(mode="after")
    def _total_quantity_within_limit(self) -> "CreateOrderRequest":
        total_qty = sum(i.quantity for i in self.items)
        if total_qty > 30:
            raise ValueError("Orders are limited to 30 items at a time")
        return self
```

Add `model_validator` to the `pydantic` import line. Add two response fields:

```python
class OrderResponse(BaseModel):
    id: uuid.UUID
    guest_session_id: uuid.UUID
    restaurant_id: uuid.UUID
    table_id: uuid.UUID | None
    status: str
    total: Decimal
    currency: str
    idempotency_key: str
    allergen_conflict_acknowledged: bool
    allergens_to_avoid: list[str]
    dietary_preferences: list[str]
    placed_at: datetime
    bumped_at: datetime | None
    items: list[OrderItemResponse]
    over_first_order_cap: bool = False

    model_config = ConfigDict(from_attributes=True, extra="forbid")
```

- [ ] **Step 2: Write the failing tests**

Add to `services/api/tests/test_orders.py`, following the existing fixture conventions in that
file (read it first for the exact helper names — `create_order_payload`, `guest_session`,
table fixtures, etc.):

```python
async def test_order_waits_for_table_to_open(client, guest_session_no_sitting):
    resp = await client.post("/api/orders", json=order_payload(), headers=guest_headers(guest_session_no_sitting))
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "table_not_open"


async def test_first_order_is_pending_approval(client, guest_session_table_open):
    resp = await client.post("/api/orders", json=order_payload(), headers=guest_headers(guest_session_table_open))
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending_approval"


async def test_second_order_of_sitting_goes_straight_to_kitchen(client, guest_session_table_open, approved_first_order):
    resp = await client.post("/api/orders", json=order_payload(idempotency_key="order-2"), headers=guest_headers(guest_session_table_open))
    assert resp.status_code == 201
    assert resp.json()["status"] == "placed"


async def test_code_required_but_missing_is_refused(client, guest_session_code_required_table):
    resp = await client.post("/api/orders", json=order_payload(), headers=guest_headers(guest_session_code_required_table))
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "code_required"


async def test_wrong_code_five_times_locks_out(client, guest_session_code_required_table):
    for _ in range(5):
        resp = await client.post(
            "/api/orders",
            json=order_payload(code="0000"),
            headers=guest_headers(guest_session_code_required_table),
        )
        assert resp.status_code == 403
    resp = await client.post(
        "/api/orders",
        json=order_payload(code="0000"),
        headers=guest_headers(guest_session_code_required_table),
    )
    assert resp.status_code == 429


async def test_approve_first_order_sends_it_to_kitchen(client, owner_token, pending_order):
    resp = await client.post(
        f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/approve",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "placed"


async def test_decline_first_order_cancels_it(client, owner_token, pending_order):
    resp = await client.post(
        f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/decline",
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_double_approve_is_idempotent(client, owner_token, pending_order):
    first = await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/approve", headers=auth_headers(owner_token))
    second = await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/approve", headers=auth_headers(owner_token))
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "placed"


async def test_approve_then_decline_the_loser_sees_already_handled(client, owner_token, pending_order):
    await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/approve", headers=auth_headers(owner_token))
    resp = await client.post(f"/api/restaurants/{RESTAURANT_SLUG}/orders/{pending_order.id}/decline", headers=auth_headers(owner_token))
    assert resp.status_code == 409
    assert "Already handled" in resp.json()["detail"]


async def test_fourth_order_in_five_minutes_is_rate_limited(client, guest_session_table_open):
    for i in range(3):
        resp = await client.post("/api/orders", json=order_payload(idempotency_key=f"k{i}"), headers=guest_headers(guest_session_table_open))
        assert resp.status_code in (200, 201)
    resp = await client.post("/api/orders", json=order_payload(idempotency_key="k4"), headers=guest_headers(guest_session_table_open))
    assert resp.status_code == 429


async def test_first_order_over_cap_still_created_but_flagged(client, guest_session_table_open, cheap_menu):
    resp = await client.post(
        "/api/orders",
        json=order_payload(items=[{"menu_item_id": str(cheap_menu.id), "quantity": 20}]),
        headers=guest_headers(guest_session_table_open),
    )
    assert resp.status_code == 201
    assert resp.json()["over_first_order_cap"] is True
    assert resp.json()["status"] == "pending_approval"
```

(These fixtures — `guest_session_no_sitting`, `guest_session_table_open`,
`guest_session_code_required_table`, `approved_first_order`, `pending_order`, `cheap_menu`,
`order_payload`, `guest_headers` — follow the naming and construction style already used in
`test_orders.py`; build each on top of the existing fixtures in that file (e.g. there's almost
certainly already a `guest_session` fixture to extend with an open or unopened sitting) rather
than inventing a new pattern.)

- [ ] **Step 3: Run to verify they fail**

Run: `pytest services/api/tests/test_orders.py -v -k "sitting or pending_approval or approve or decline or code or cap or rate_limited"`
Expected: FAIL — routes and behaviour don't exist yet.

- [ ] **Step 4: Implement table-state checks and limits in `create_order`**

In `services/api/src/routers/orders.py`, add imports:
`from src.request_limits import enforce_session_limit`,
`from src.services.sitting import get_open_sitting`, and the `TableSitting` model.

Insert, right after step 4 (`restaurant = res_rest.scalar_one()`) and before step 4b, a new
block that only applies to table orders (not counter — counters have no sitting):

```python
    sitting: TableSitting | None = None
    is_first_order_of_sitting = False
    if session.table_id is not None and not at_counter_placeholder:
        ...
```

This needs `at_counter` computed earlier than it currently is — move the existing `at_counter`
computation (currently just above `if at_counter:` near step 6) up to immediately after step 4,
and build the sitting logic right after it:

```python
    at_counter = session.table_id is not None and (
        await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
        == "counter"
    )

    sitting: TableSitting | None = None
    is_first_order_of_sitting = False
    if session.table_id is not None and not at_counter:
        await enforce_session_limit(
            str(session.id), "order_create", limit=3, window_s=300,
            detail="You're ordering quickly! Please wait a moment and try again.",
        )
        sitting = await get_open_sitting(db, session.table_id)
        if sitting is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "table_not_open"},
            )
        if sitting.code_required and session.sitting_id != sitting.id:
            if not payload.code:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "code_required"}
                )
            lock_key = f"code_lock:{session.id}"
            locked = await redis_client.get(lock_key)
            if locked:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many wrong codes — please wait a minute and ask your waiter.",
                )
            if payload.code != sitting.code:
                attempts_key = f"code_attempts:{session.id}"
                attempts = await redis_client.incr(attempts_key)
                if attempts == 1:
                    await redis_client.expire(attempts_key, 300)
                if attempts >= 5:
                    await redis_client.set(lock_key, "1", ex=60)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail={"error": "code_required"}
                )
            session.sitting_id = sitting.id
        elif session.sitting_id != sitting.id:
            session.sitting_id = sitting.id
        is_first_order_of_sitting = (
            await db.scalar(
                select(Order.id).where(
                    Order.sitting_id == sitting.id, Order.status != "cancelled"
                ).limit(1)
            )
        ) is None
```

Then remove the now-duplicate `at_counter = ...` block that currently sits just above
`if at_counter:` (the one being replaced), leaving only the `if at_counter: ... elif
session.table_id: ... else: ...` bill-opening logic that follows it.

Compute the over-cap flag (needs the menu average, and only matters for the first order):

```python
    over_first_order_cap = False
    if is_first_order_of_sitting:
        avg_price = await db.scalar(
            select(func.avg(MenuItem.price)).where(
                MenuItem.restaurant_id == session.restaurant_id, MenuItem.deleted_at.is_(None)
            )
        )
        if avg_price:
            cap = avg_price * restaurant.first_order_cap_multiplier
            over_first_order_cap = total > cap
```

Add `func` to the `sqlalchemy` import if not already imported in this file (check first), and
`MenuItem.price` must exist already (it's used elsewhere in the file for menu fetching).

Set the order's `status` and `sitting_id` when constructing `Order(...)`:

```python
    order = Order(
        guest_session_id=session.id,
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        bill_id=bill.id if bill else None,
        sitting_id=sitting.id if sitting else None,
        status=(
            "pending_approval" if is_first_order_of_sitting
            else "awaiting_payment" if at_counter
            else "placed"
        ),
        total=total,
        ...  # unchanged
    )
```

And after commit, only publish the kitchen/order-placed events when the order actually reached
`placed` status — a `pending_approval` order isn't in the kitchen yet, but it is a Floor-view
change:

```python
    if final_order.status == "placed":
        order_event = json.dumps({"event": "order_placed", "order_id": str(final_order.id)})
        await publish_event(f"kitchen:{final_order.restaurant_id}", order_event)
        await publish_event(f"orders:{final_order.id}", order_event)
    elif final_order.status == "pending_approval":
        await publish_event(
            f"kitchen:{final_order.restaurant_id}",
            json.dumps({"event": "approval_needed", "table_id": str(final_order.table_id)}),
        )
        await publish_event(
            f"orders:{final_order.id}",
            json.dumps({"event": "order_pending_approval", "order_id": str(final_order.id)}),
        )
    if bill_created:
        ...  # unchanged
```

Finally, include `over_first_order_cap` in the returned response — extend `order_response` (near
the top of the file) to accept and pass it through, or simpler: build the response dict directly
in `create_order`'s return instead of via the shared `order_response` helper when this flag is
relevant. The least invasive option, consistent with the existing `order_response` helper
pattern of overriding one field: give `order_response` an optional second argument:

```python
async def order_response(
    db: AsyncSession, order: Order, over_first_order_cap: bool = False
) -> OrderResponse:
    """OrderResponse with the venue currency, loaded explicitly (relationships are lazy="raise")."""
    currency = await db.scalar(
        select(Restaurant.currency).where(Restaurant.id == order.restaurant_id)
    )
    fields = {
        name: getattr(order, name) for name in OrderResponse.model_fields
        if name not in ("currency", "over_first_order_cap")
    }
    return OrderResponse.model_validate(
        {**fields, "currency": currency, "over_first_order_cap": over_first_order_cap},
        from_attributes=True,
    )
```

And update the final `return await order_response(db, final_order)` in `create_order` to
`return await order_response(db, final_order, over_first_order_cap)`. Every other call to
`order_response` elsewhere in the file keeps its default `False`.

- [ ] **Step 5: Add the approve/decline endpoints**

These belong under the restaurant-scoped prefix, not the guest-scoped `/api/orders` prefix used
by the rest of this file — add them to `services/api/src/routers/floor.py` instead (same prefix
as `open_table`/`close_table`, and the same file that already imports `Order`). Add:

```python
@router.post(
    "/orders/{order_id}/approve",
    response_model=OrderResponse,
    responses={**RESPONSES, 409: {"description": "Not waiting for approval"}},
)
async def approve_order(
    order_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    rid = access.restaurant.id
    order = (
        await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order_id, Order.restaurant_id == rid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status == "placed":
        return await order_response(db, order)  # already approved — idempotent replay
    if order.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already handled")
    order.status = "placed"
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_approved",
            actor=f"user:{access.user.id}",
            payload={"order_id": str(order.id)},
        )
    )
    await db.commit()
    event = json.dumps({"event": "order_placed", "order_id": str(order.id)})
    await publish_event(f"kitchen:{rid}", event)
    await publish_event(f"orders:{order.id}", event)
    return await order_response(db, order)


@router.post(
    "/orders/{order_id}/decline",
    response_model=OrderResponse,
    responses={**RESPONSES, 409: {"description": "Already handled"}},
)
async def decline_order(
    order_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    rid = access.restaurant.id
    order = (
        await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order_id, Order.restaurant_id == rid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already handled")
    now = await db.scalar(select(func.clock_timestamp()))
    order.status = "cancelled"
    order.voided_at = now
    order.void_reason = "Declined by waiter"
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_declined",
            actor=f"user:{access.user.id}",
            payload={"order_id": str(order.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"orders:{order.id}",
        json.dumps({"event": "order_declined", "order_id": str(order.id)}),
    )
    return await order_response(db, order)
```

This needs `order_response` and `OrderResponse` imported into `floor.py` from
`src.routers.orders` and `src.schemas.orders` respectively, plus `selectinload` from
`sqlalchemy.orm`. Circular-import check: `orders.py` doesn't import anything from `floor.py`, so
`floor.py` importing from `orders.py` is safe.

- [ ] **Step 6: Run to verify everything passes**

Run: `pytest services/api/tests/test_orders.py services/api/tests/test_floor.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src/routers/orders.py services/api/src/routers/floor.py \
  services/api/src/schemas/orders.py services/api/tests/test_orders.py
git commit -m "feat(api): first-order approval, sitting/code checks, and order rate/size limits

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Close the sitting on settle, void-ends-bill, and in the guest status check

**Files:**
- Modify: `services/api/src/services/bills.py` (`settle_bill`)
- Modify: `services/api/src/routers/bills.py` (the void-order endpoint's `if empties:` branch)
- Modify: `services/api/src/routers/guest.py` (so a guest's `GET` session/menu status reflects
  `sitting_open` for the waiting-bar / live-SSE behaviour in Task 11)
- Test: `services/api/tests/test_bills.py`

- [ ] **Step 1: Write the failing tests**

Add to `services/api/tests/test_bills.py`:

```python
async def test_settle_closes_the_table_sitting(client, owner_token, open_bill_with_sitting):
    resp = await client.post(
        f"/api/restaurants/{RESTAURANT_SLUG}/bills/{open_bill_with_sitting.id}/settle",
        json=settle_payload(open_bill_with_sitting),
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200
    sitting = await get_sitting_for_table(open_bill_with_sitting.table_id)
    assert sitting.closed_at is not None
    assert sitting.close_reason == "settled"


async def test_voiding_the_last_order_closes_the_sitting(client, owner_token, bill_one_order_with_sitting):
    order = bill_one_order_with_sitting.orders[0]
    resp = await client.post(
        f"/api/restaurants/{RESTAURANT_SLUG}/bills/{bill_one_order_with_sitting.id}/orders/{order.id}/void",
        json={"reason": "Guest left", "acknowledge_claim": False},
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 200
    sitting = await get_sitting_for_table(bill_one_order_with_sitting.table_id)
    assert sitting.closed_at is not None
    assert sitting.close_reason == "cancelled"
```

(Build `open_bill_with_sitting`, `bill_one_order_with_sitting`, `get_sitting_for_table`, and
`settle_payload` on top of whatever fixtures `test_bills.py` already has for an open bill with
orders — read the file first for the real void-endpoint path and payload shape, since the exact
URL and body were inferred from `routers/bills.py` and should be checked against that file's
existing void tests.)

- [ ] **Step 2: Run to verify they fail**

Run: `pytest services/api/tests/test_bills.py -v -k "closes_the_table_sitting or closes_the_sitting"`
Expected: FAIL — sitting stays open.

- [ ] **Step 3: Hook the close into `settle_bill`**

In `services/api/src/services/bills.py`, add
`from src.services.sitting import close_sitting_for_table` to the imports. In `settle_bill`,
right after `bill.settled_at = now` and the other settle-field assignments (before the function
proceeds to release counter orders), add, only when the bill has a table:

```python
    if bill.table_id is not None:
        await close_sitting_for_table(db, bill.table_id, "settled", now)
```

This is a no-op for counter bills' "tables" in the sense that counter tables never have an open
`table_sitting` row (sittings are only opened via the Floor `Open table` action, which per Task 6
only targets `kind='table'` rows), so the call is safe to make unconditionally whenever
`table_id` is set.

- [ ] **Step 4: Hook the close into the void-ends-bill path**

In `services/api/src/routers/bills.py`, add the same import. In the void-order endpoint's
`if empties:` block (around where `bill.status = "cancelled"` / `bill.cancelled_at = now` are
set), add:

```python
    if empties:
        bill.status = "cancelled"
        bill.cancelled_at = now
        bill.cancelled_by = access.user.id
        bill.cancel_reason = ALL_VOIDED
        if bill.table_id is not None:
            await close_sitting_for_table(db, bill.table_id, "cancelled", now)
        db.add(
            AuditLog(...)  # unchanged
        )
```

- [ ] **Step 5: Expose `sitting_open` on the guest-facing status**

In `services/api/src/routers/guest.py`, find `get_guest_session` (the `GET` endpoint guests poll
for their own session state — check its current response schema in `schemas/guest.py`) and add
a `sitting_open: bool` field, computed the same way as `get_open_sitting` but without taking the
`FOR UPDATE` lock (this is a read path, not a mutation):

```python
    sitting_open = False
    if session.table_id is not None:
        sitting_open = (
            await db.scalar(
                select(TableSitting.id).where(
                    TableSitting.table_id == session.table_id, TableSitting.closed_at.is_(None)
                ).limit(1)
            )
        ) is not None
```

Add the corresponding field to whatever response schema `get_guest_session` uses in
`schemas/guest.py`, following that schema's existing style, and import `TableSitting` into
`guest.py`.

- [ ] **Step 6: Run to verify everything passes**

Run: `pytest services/api/tests/test_bills.py services/api/tests/test_guest.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/src/services/bills.py services/api/src/routers/bills.py \
  services/api/src/routers/guest.py services/api/src/schemas/guest.py \
  services/api/tests/test_bills.py
git commit -m "feat(api): settling or voiding-out a table bill closes its sitting

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: `services/service_report.py`, schema, and router endpoint

**Files:**
- Create: `services/api/src/services/service_report.py`
- Modify: `services/api/src/schemas/` (new file `service_report.py`)
- Modify: `services/api/src/routers/owner.py` (add the report endpoint)
- Test: `services/api/tests/test_service_report.py`

- [ ] **Step 1: Write the failing unit tests for the pure computation**

```python
"""Tests for the daily service report: pure functions over plain sitting/order facts."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.services.service_report import SittingRecord, build_report

T0 = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def _sitting(opened_offset_min, closed_offset_min, first_order_offset_min=None, bill_requested_offset_min=None, settled_offset_min=None):
    opened = T0 + timedelta(minutes=opened_offset_min)
    return SittingRecord(
        opened_at=opened,
        closed_at=T0 + timedelta(minutes=closed_offset_min),
        close_reason="settled",
        first_order_placed_at=(opened + timedelta(minutes=first_order_offset_min)) if first_order_offset_min else None,
        bill_requested_at=(opened + timedelta(minutes=bill_requested_offset_min)) if bill_requested_offset_min else None,
        settled_at=(opened + timedelta(minutes=settled_offset_min)) if settled_offset_min else None,
        source="live",
    )


def test_counts_tables_served_and_average_table_time():
    sittings = [_sitting(0, 40), _sitting(60, 120)]
    report = build_report(sittings)
    assert report.tables_served == 2
    assert report.average_table_time == timedelta(minutes=50)


def test_average_wait_to_first_order():
    sittings = [_sitting(0, 40, first_order_offset_min=5), _sitting(60, 120, first_order_offset_min=15)]
    report = build_report(sittings)
    assert report.average_wait_to_first_order == timedelta(minutes=10)


def test_sittings_without_a_stage_timestamp_are_excluded_from_that_averages_only():
    sittings = [_sitting(0, 40, first_order_offset_min=5), _sitting(60, 120)]  # no order on 2nd
    report = build_report(sittings)
    assert report.tables_served == 2  # still counted for table time
    assert report.average_wait_to_first_order == timedelta(minutes=5)  # only the 1st counts


def test_simulated_sittings_counted_separately():
    live = _sitting(0, 40, first_order_offset_min=5)
    sim = SittingRecord(
        opened_at=T0, closed_at=T0 + timedelta(minutes=30), close_reason="settled",
        first_order_placed_at=None, bill_requested_at=None, settled_at=None, source="simulated",
    )
    report = build_report([live, sim])
    assert report.tables_served == 1
    assert report.simulated_sittings == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest services/api/tests/test_service_report.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write `services/service_report.py`**

```python
"""Daily service report: pure aggregation over recorded sitting and order timestamps."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SittingRecord:
    opened_at: datetime
    closed_at: datetime
    close_reason: str
    first_order_placed_at: datetime | None
    bill_requested_at: datetime | None
    settled_at: datetime | None
    source: str  # "live" | "simulated" — mirrors Order.source


@dataclass(frozen=True)
class ServiceReport:
    tables_served: int
    simulated_sittings: int
    average_table_time: timedelta | None
    average_wait_to_first_order: timedelta | None
    average_wait_bill_to_settle: timedelta | None


def _average(values: list[timedelta]) -> timedelta | None:
    if not values:
        return None
    return sum(values, timedelta()) / len(values)


def build_report(sittings: list[SittingRecord]) -> ServiceReport:
    live = [s for s in sittings if s.source == "live"]
    simulated = [s for s in sittings if s.source == "simulated"]
    table_times = [s.closed_at - s.opened_at for s in live]
    first_order_waits = [
        s.first_order_placed_at - s.opened_at for s in live if s.first_order_placed_at is not None
    ]
    settle_waits = [
        s.settled_at - s.bill_requested_at
        for s in live
        if s.bill_requested_at is not None and s.settled_at is not None
    ]
    return ServiceReport(
        tables_served=len(live),
        simulated_sittings=len(simulated),
        average_table_time=_average(table_times),
        average_wait_to_first_order=_average(first_order_waits),
        average_wait_bill_to_settle=_average(settle_waits),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest services/api/tests/test_service_report.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Write the schema**

Create `services/api/src/schemas/service_report.py`:

```python
"""Daily service report schema."""

from datetime import timedelta

from pydantic import BaseModel


class ServiceReportResponse(BaseModel):
    tables_served: int
    simulated_sittings: int
    average_table_time_seconds: int | None
    average_wait_to_first_order_seconds: int | None
    average_wait_bill_to_settle_seconds: int | None
    summary: str  # one line, phrased by the model, checked against these numbers


def to_response(report, summary: str) -> ServiceReportResponse:
    def secs(td: timedelta | None) -> int | None:
        return int(td.total_seconds()) if td is not None else None

    return ServiceReportResponse(
        tables_served=report.tables_served,
        simulated_sittings=report.simulated_sittings,
        average_table_time_seconds=secs(report.average_table_time),
        average_wait_to_first_order_seconds=secs(report.average_wait_to_first_order),
        average_wait_bill_to_settle_seconds=secs(report.average_wait_bill_to_settle),
        summary=summary,
    )
```

- [ ] **Step 6: Add the router endpoint**

Read `services/api/src/routers/owner.py` first to match its existing query style for pulling
per-restaurant data (it already has `list_owner_menu_items`, `list_my_restaurants`, etc. — follow
the same `member_access` + `AsyncSession` dependency pattern used throughout this file and in
`floor.py`). Add:

```python
@router.get(
    "/service-report",
    response_model=ServiceReportResponse,
    responses=RESPONSES,
)
async def get_service_report(
    day: date,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> ServiceReportResponse:
    rid = access.restaurant.id
    tz = ZoneInfo(access.restaurant.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    rows = (
        await db.execute(
            select(
                TableSitting.opened_at,
                TableSitting.closed_at,
                TableSitting.close_reason,
                func.min(Order.placed_at).label("first_order_placed_at"),
                Bill.bill_requested_at,
                Bill.settled_at,
                func.coalesce(func.bool_or(Order.source == "simulated"), False).label(
                    "is_simulated"
                ),
            )
            .select_from(TableSitting)
            .join(DiningTable, DiningTable.id == TableSitting.table_id)
            .outerjoin(Order, Order.sitting_id == TableSitting.id)
            .outerjoin(Bill, Bill.table_id == TableSitting.table_id)
            .where(
                DiningTable.restaurant_id == rid,
                TableSitting.closed_at.is_not(None),
                TableSitting.closed_at >= start,
                TableSitting.closed_at < end,
            )
            .group_by(
                TableSitting.id, TableSitting.opened_at, TableSitting.closed_at,
                TableSitting.close_reason, Bill.bill_requested_at, Bill.settled_at,
            )
        )
    ).all()
    records = [
        SittingRecord(
            opened_at=r.opened_at,
            closed_at=r.closed_at,
            close_reason=r.close_reason,
            first_order_placed_at=r.first_order_placed_at,
            bill_requested_at=r.bill_requested_at,
            settled_at=r.settled_at,
            source="simulated" if r.is_simulated else "live",
        )
        for r in rows
    ]
    report = build_report(records)
    summary = await narrative.phrase_service_report(report)  # follow narrative.py's existing
    # pattern for phrasing a report: pass only the computed numbers, never guest data, and run
    # the result through the existing number-consistency check before returning it.
    return to_response(report, summary)
```

This last call, `narrative.phrase_service_report`, doesn't exist yet — add it to
`services/api/src/services/narrative.py` following the exact pattern its other `phrase_*`
functions already use (read that file first: it already has at least one function that takes
computed numbers, calls the inference client with `LLM_PROVIDER` respected, and validates the
response against the numbers before returning). If building that symmetry turns out to need
more than a few lines because `narrative.py`'s existing functions are tightly coupled to a
different report's shape, fall back to a fixed template string built from the numbers (e.g.
`f"{report.tables_served} tables served today, averaging {avg} per table."`) for this task and
leave model-phrased summaries as a follow-up — the numbers themselves must never depend on this
decision.

- [ ] **Step 7: Add integration tests for the endpoint** (extending the same
  `test_service_report.py`, or a new router-level test if this repo keeps unit and router tests
  separate — check the convention used for `test_floor.py` vs its router tests in Task 6).

- [ ] **Step 8: Run to verify everything passes**

Run: `pytest services/api/tests/test_service_report.py -v`

- [ ] **Step 9: Commit**

```bash
git add services/api/src/services/service_report.py services/api/src/schemas/service_report.py \
  services/api/src/routers/owner.py services/api/src/services/narrative.py \
  services/api/tests/test_service_report.py
git commit -m "feat(api): daily service report from recorded sitting and order timestamps

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: `packages/api-client` regeneration

**Files:**
- Modify: generated files under `packages/api-client/src/` (regenerated, not hand-edited)

- [ ] **Step 1: Regenerate**

Run whatever command this repo already uses to regenerate the client from the OpenAPI schema
(check `packages/api-client/package.json` scripts, or how the earlier `6113b2a` commit — "api
client regenerated" — was produced; likely `npm run generate` from that package, with the API
running).

- [ ] **Step 2: Verify the new types appear**

Run: `grep -r "pending_approval\|table_sitting\|OpenSittingResponse" packages/api-client/src | head -5`
Expected: non-empty — the new status value and schemas are present.

- [ ] **Step 3: Commit**

```bash
git add packages/api-client/src
git commit -m "chore: regenerate api-client for safer table ordering

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 11: Owner-web — Floor tile actions and states

**Files:**
- Modify: `apps/owner-web/src/lib/floor.ts`
- Modify: `apps/owner-web/src/lib/floor.test.ts`
- Modify: `apps/owner-web/src/app/(dashboard)/floor/page.tsx`

- [ ] **Step 1: Extend the types and pure helpers, with failing tests first**

Add to `floor.test.ts`:

```typescript
it("labels the new approval_needed state", () => {
  expect(stateLabel("approval_needed")).toBe("Approve order");
});

it("shows a waiting-to-open badge text", () => {
  expect(waitingForOpenText(true)).toBe("Guests waiting to order");
  expect(waitingForOpenText(false)).toBeNull();
});
```

Run: `npx vitest run apps/owner-web/src/lib/floor.test.ts` — expect FAIL (new exports missing).

In `floor.ts`:

```typescript
export type FloorState = "free" | "seated" | "ordered" | "served" | "paying" | "needs_clearing" | "called" | "approval_needed";
```

Add to `FloorTile` interface:

```typescript
export interface FloorTile {
  // ...existing fields unchanged...
  sitting_open: boolean;
  waiting_for_open: boolean;
  pending_order_id: string | null;
  pending_order_total: string | null;
  pending_order_items: number | null;
}
```

Add to `STATES`:

```typescript
const STATES: Record<FloorState, { label: string; icon: string }> = {
  // ...existing entries unchanged...
  approval_needed: { label: "Approve order", icon: "⚠" },
};
```

Add:

```typescript
export const waitingForOpenText = (waiting: boolean): string | null =>
  waiting ? "Guests waiting to order" : null;
```

Run: `npx vitest run apps/owner-web/src/lib/floor.test.ts` — expect PASS.

- [ ] **Step 2: Add tile actions to the Floor page**

Read `apps/owner-web/src/app/(dashboard)/floor/page.tsx` in full first (it's 210 lines — small
enough to read whole) to match its existing patterns for a tile action (it already has a
"clear table" and "resolve call" action — follow the same fetch-then-refresh approach, same
error toast handling, same button placement convention).

Add, for a `free` tile with no `sitting_open`: an **"Open table"** button that
`POST`s `/api/restaurants/{slug}/tables/{id}/sitting`, then shows the returned `code` (if any) in
a small dismissable banner reading "Code: 1234 — tell your guests" (staff-only screen, never
guest-facing).

For a tile where `sitting_open` is true: a **"Close table"** button (`DELETE` on the same URL),
disabled with a tooltip "Settle the bill first" when the tile's existing `bill_id` is set.

For `state === "approval_needed"`: render the pending order's item count and total (already on
the tile from Task 6) with **"Approve"** and **"Not now"** buttons calling
`POST /api/restaurants/{slug}/orders/{pending_order_id}/approve` and `/decline`. On a 409 from
either, show "Already handled" (not a generic error) and refresh the tile list.

For `waiting_for_open === true` on a `seated`-state tile: render the pulsing badge text from
`waitingForOpenText(true)`.

Follow the file's existing `fetch` + `mutate`/refresh pattern exactly — don't introduce a new
data-fetching approach for these new actions.

- [ ] **Step 3: Run the frontend test suite and the dev server smoke check**

Run: `npx vitest run apps/owner-web/src/lib/floor.test.ts`
Expected: PASS. Then start the owner-web dev server (`LLM_PROVIDER=mock DEMO_MODE=true make up`,
or whatever this repo's documented manual-check command is) and visually confirm the new buttons
appear on a free and on a seated table tile.

- [ ] **Step 4: Commit**

```bash
git add apps/owner-web/src/lib/floor.ts apps/owner-web/src/lib/floor.test.ts \
  "apps/owner-web/src/app/(dashboard)/floor/page.tsx"
git commit -m "feat(web): Open/Close table and Approve/Not now on the Floor view

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 12: Owner-web — daily service report section

**Files:**
- Modify: `apps/owner-web/src/app/(dashboard)/floor/page.tsx` or a new
  `apps/owner-web/src/app/(dashboard)/reports/page.tsx` (check first whether a Reports page
  already exists — the earlier menu-engineering/forecast work referenced in the codebase map
  suggests one might: `grep -rl "Reports" apps/owner-web/src/app`)

- [ ] **Step 1: Find or create the Reports page**

Run: `grep -rl "Reports" apps/owner-web/src/app`. If a Reports page/section exists, add a new
card to it, following its existing card component pattern. If none exists, create
`apps/owner-web/src/app/(dashboard)/reports/page.tsx` modelled directly on the structure of
`floor/page.tsx` (same data-fetching and layout conventions), plus a nav entry wherever
`AppShell`'s `NavGroup`/`NavItem` list is defined (check `packages/ui/src/` or the dashboard
layout file for where Floor's own nav entry is registered, and add Reports the same way).

- [ ] **Step 2: Build the card**

A date picker (default: today, in the venue's timezone) and a card showing, from
`GET /api/restaurants/{slug}/service-report?day=YYYY-MM-DD`:
tables served, average table time, average wait to first order, average wait bill-to-settle (all
formatted with the existing `formatElapsed`-style helper from `floor.ts`, reused rather than
duplicated), and the one-line `summary` text.

- [ ] **Step 3: Manual verification**

Start the dev server and confirm the report loads for today and for a day with no sittings
(shows zeros/blank averages, not an error).

- [ ] **Step 4: Commit**

```bash
git add apps/owner-web/src/app
git commit -m "feat(web): daily service report card in the owner app

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 13: Guest-web — waiting bar, code modal, approval status, limit messages

**Files:**
- Modify: `apps/guest-web/src/app/[lang]/menu/page.tsx`
- Modify: `apps/guest-web/src/app/[lang]/orders/[id]/page.tsx`
- Modify: `apps/guest-web/src/lib/` (wherever `CartState`/order-submission logic lives — check
  `apps/guest-web/src/lib/` listing from the codebase map: `CartItem`, `CartState` are there)
- Possibly create: `apps/guest-web/src/components/CodeEntry.tsx` (a 4-box numeric input, modelled
  on the existing `AllergenChip`/`PaySheet` component style in
  `apps/guest-web/src/components/`)

- [ ] **Step 1: Read the menu page and the SSE hook in full**

Read `apps/guest-web/src/app/[lang]/menu/page.tsx` (473 lines) and
`apps/guest-web/src/hooks/useSse` (or the `SseManager`/`UseSseOptions` listed in the codebase
map) before writing anything, to match the existing bottom-bar and SSE-driven re-render pattern
exactly.

- [ ] **Step 2: Waiting-for-table bar**

When the guest-session status (now including `sitting_open`, from Task 8 Step 5) is `false`:
replace the existing order button with a bar reading "Your table will be ready in a moment. A
waiter is on the way." plus the existing **Call waiter** button (already implemented — just
needs to stay visible/enabled here, unlike the order button). Drive this off the same SSE channel
the page already subscribes to for menu/order updates, adding the `sitting_open` field to
whatever payload that channel already carries, or polling the existing guest-session `GET` on
the same interval the page already uses for something else (match whichever mechanism the page
already has — don't add a second SSE channel if one re-render path already exists).

- [ ] **Step 3: Code entry modal**

Create `CodeEntry.tsx`: four single-digit boxes, auto-advancing focus, a "Submit" button disabled
until all four are filled. Shown when an order submission returns
`{"error": "code_required"}`. On submit, retry the same order submission with the `code` field
set. On a repeated `{"error": "code_required"}` response, show "That code didn't match, please
ask your waiter" and clear the boxes. On a `429`, show "Too many tries — please wait a minute and
ask your waiter" and disable the modal's retry for 60 seconds (client-side cosmetic only; the
server is the real enforcement from Task 7).

- [ ] **Step 4: Pending-approval and declined status**

On the order detail page (`orders/[id]/page.tsx`), add a status rendering for
`status === "pending_approval"`: "Sent! Your waiter is confirming your order." with the existing
item/total summary. Drive the transition to `status === "placed"` ("Confirmed, it's being
cooked") off the existing SSE order-status subscription (`UseSseOptions` already listed against
`orders` in the codebase map — reuse it, don't add a new one). For a declined order
(`status === "cancelled"` with `void_reason === "Declined by waiter"` — check this field is
exposed on the order response the page already fetches, add it to the TS type if not): show
"Your waiter will come to your table to help." and return the guest to the menu with their cart
items restored (read from the now-cancelled order's items and re-add them to the cart state in
`apps/guest-web/src/lib/`, following whatever `CartState` already exposes for rehydrating a
cart).

- [ ] **Step 5: Limit and closed-table messages**

On a `409` with `{"error": "table_not_open"}` from an order submission (a race: the bar should
already have prevented this, but handle it anyway) and on a `413`-style over-30-items response
from the schema validator in Task 7 (actually a `422` — Pydantic validation error; check the
exact status FastAPI returns for a `model_validator` `ValueError` and match it), show "That's a
big order! Your waiter will confirm it with you." rather than a generic error, when the response
indicates the 30-item cap. For the `over_first_order_cap` flag on a successful `201` response,
show the same "That's a big order!" message alongside the pending-approval status. When the
sitting has closed mid-session (guest-session status flips `sitting_open` back to `false` with a
`close_reason` present, or an order submission gets `table_not_open` after previously ordering
successfully), show "Thanks for visiting!" with a link back to the menu, replacing the ordering
UI entirely.

- [ ] **Step 6: Manual verification**

Run the e2e test from Task 14 as the real verification for this task — these are UI states that
are easiest to confirm end-to-end rather than in isolation. Before that exists, do one manual
pass through the dev server: scan a table before it's open, have it open from another
owner-web tab, place an order, approve it from owner-web, confirm the guest page updates without
a reload.

- [ ] **Step 7: Commit**

```bash
git add apps/guest-web/src/app apps/guest-web/src/components/CodeEntry.tsx apps/guest-web/src/lib
git commit -m "feat(web): guest screens for waiting, code entry, approval and order limits

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 14: End-to-end test and CLAUDE.md update

**Files:**
- Modify: `e2e/self-service.spec.ts`
- Modify: `e2e/helpers.ts` (add helpers for opening a table and approving an order, following the
  existing helper style in that file)
- Modify: `C:\Users\MSI\Source Code\Mise\CLAUDE.md`

- [ ] **Step 1: Read `e2e/self-service.spec.ts` and `e2e/helpers.ts` in full**

These already exist from the previous Priority 2 work — match their Playwright patterns (how a
guest page and an owner page are driven in the same test, how the existing call-waiter/pay-at-
table flows are expressed) exactly rather than introducing a new style.

- [ ] **Step 2: Add the sitting flow test**

```typescript
test("safer table ordering: scan before open, approval, second order, idle-free close", async ({ browser }) => {
  const guestPage = await (await browser.newContext()).newPage();
  const ownerPage = await (await browser.newContext()).newPage();

  await loginOwner(ownerPage);
  const table = await pickFreeTable(ownerPage);

  await guestPage.goto(guestMenuUrl(table.qrToken));
  await expect(guestPage.getByText("A waiter is on the way")).toBeVisible();
  await addItemToCart(guestPage, "Chicken Karahi");
  await expect(guestPage.getByRole("button", { name: /place order/i })).toBeDisabled();

  await openTable(ownerPage, table.label);
  await expect(guestPage.getByRole("button", { name: /place order/i })).toBeEnabled({ timeout: 10_000 });

  await guestPage.getByRole("button", { name: /place order/i }).click();
  await expect(guestPage.getByText("confirming your order")).toBeVisible();

  await approveFirstOrder(ownerPage, table.label);
  await expect(guestPage.getByText("being cooked")).toBeVisible({ timeout: 10_000 });

  await addItemToCart(guestPage, "Garlic Naan");
  await guestPage.getByRole("button", { name: /place order/i }).click();
  await expect(guestPage.getByText("being cooked")).toBeVisible();

  await payAtTable(guestPage, "cash");
  await settleBillAsOwner(ownerPage, table.label);

  await expect(guestPage.getByText("Paid")).toBeVisible();
  await expect(ownerPage.getByRole("button", { name: /open table/i, exact: false })).toBeVisible({
    timeout: 10_000,
  }); // the tile is free again
});
```

- [ ] **Step 3: Add the dropped-connection run**

```typescript
test("safer table ordering: a dropped connection never double-places the first order", async ({ browser, context }) => {
  const guestPage = await (await browser.newContext()).newPage();
  const ownerPage = await (await browser.newContext()).newPage();
  await loginOwner(ownerPage);
  const table = await pickFreeTable(ownerPage);
  await openTable(ownerPage, table.label);

  await guestPage.goto(guestMenuUrl(table.qrToken));
  await addItemToCart(guestPage, "Chicken Karahi");
  await guestPage.context().setOffline(true);
  await guestPage.getByRole("button", { name: /place order/i }).click().catch(() => {});
  await guestPage.context().setOffline(false);
  await guestPage.reload();
  await expect(guestPage.getByText("confirming your order")).toBeVisible({ timeout: 10_000 });

  const pendingCount = await countPendingOrders(ownerPage, table.label);
  expect(pendingCount).toBe(1);
});
```

(Add `openTable`, `approveFirstOrder`, `countPendingOrders` to `e2e/helpers.ts`, each a thin
wrapper over the owner-web UI actions added in Task 11, matching the existing helpers'
style — e.g. however `settleBillAsOwner` is already written there.)

- [ ] **Step 4: Run the e2e suite**

Run: whatever command `make verify-f` or the project's documented Playwright invocation uses for
`e2e/self-service.spec.ts` specifically, e.g. `npx playwright test e2e/self-service.spec.ts`.
Expected: all tests in the file PASS, including the two new ones.

- [ ] **Step 5: Add the CLAUDE.md rule**

In `C:\Users\MSI\Source Code\Mise\CLAUDE.md`, under `## Architecture`, add a line next to the
existing "Guests never settle bills" rule:

```
- Guest order submission never creates a `placed` order for a table without an open sitting;
  a table's first sitting order waits for one-tap staff approval before the kitchen sees it.
```

- [ ] **Step 6: Commit**

```bash
git add e2e/self-service.spec.ts e2e/helpers.ts CLAUDE.md
git commit -m "test(e2e): safer table ordering flow and a dropped-connection run

Adds the CLAUDE.md rule this feature introduces: no placed order without
an open sitting, and the first order of each sitting needs approval.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 15: Full verification

- [ ] **Step 1: Run the complete backend and frontend suites**

Run: `make ci` (lint, all Python tests in Docker, TS tests with Vitest, branding check).
Expected: all green.

- [ ] **Step 2: Run the full Phase-1-style verification against a fresh stack**

Run: `make verify-f` (or whatever this repo's full-stack verification target is called —
confirmed earlier in this project as `make verify-f`), with
`LLM_PROVIDER=mock DEMO_MODE=true`.
Expected: every step passes, including the new e2e tests from Task 14.

- [ ] **Step 3: If anything fails, fix forward in a new commit on this branch — never amend a
  pushed/shared commit, per this project's git rules**

- [ ] **Step 4: Report the final state to the user** (test counts, anything skipped, any flaky
  test observed) and hand off to `superpowers:finishing-a-development-branch` for the merge/PR
  decision — do not merge to `main` without the user's explicit choice, per `CLAUDE.md`'s
  "feature branches only" rule.
