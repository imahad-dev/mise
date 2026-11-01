"""Tests for services/sitting.py: pure idle/code logic, no DB, plus DB-backed checks below."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.service_call import ServiceCall
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.services.sitting import IDLE_TIMEOUT, generate_code, get_open_sitting, is_idle

NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def test_not_idle_just_opened():
    assert is_idle(opened_at=NOW, last_activity_at=None, now=NOW) is False


def test_idle_after_90_minutes_of_silence():
    opened = NOW - timedelta(minutes=95)
    assert is_idle(opened_at=opened, last_activity_at=None, now=NOW) is True


def test_not_idle_with_recent_activity_even_if_opened_long_ago():
    opened = NOW - timedelta(hours=3)
    recent = NOW - timedelta(minutes=10)
    assert is_idle(opened_at=opened, last_activity_at=recent, now=NOW) is False


def test_a_call_before_the_table_opened_does_not_count_as_this_partys_activity():
    """A waiter call at 11:00 from the previous party must not make a table opened at 12:00
    look idle at 12:30; the new party is idle only 90 minutes after the open."""
    opened, call = NOW, NOW - timedelta(hours=1)
    assert (
        is_idle(opened_at=opened, last_activity_at=call, now=NOW + timedelta(minutes=30)) is False
    )
    assert is_idle(opened_at=opened, last_activity_at=call, now=NOW + timedelta(minutes=90)) is True


def test_idle_timeout_is_90_minutes():
    assert timedelta(minutes=90) == IDLE_TIMEOUT


def test_generate_code_is_four_digits():
    code = generate_code()
    assert len(code) == 4
    assert code.isdigit()


async def test_a_previous_sittings_orders_do_not_leak_into_the_next_ones_idle_check(db_session):
    """Regression: _last_activity used to filter Order by table_id, so a closed sitting's old
    order could look like "recent activity" for a brand-new sitting on the same table and mask
    an idle close incorrectly in the other direction too. Here it must NOT cause a fresh sitting
    with no orders yet to be treated as having that old order's (irrelevant) activity."""
    r = Restaurant(
        name="Sitting Venue",
        slug=f"sitting-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(r)
    await db_session.flush()
    table = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    db_session.add(table)
    await db_session.flush()

    # First sitting: opened 4h ago, had an order, closed (settled) 3h ago.
    old_sitting = TableSitting(
        table_id=table.id,
        opened_at=func.now() - timedelta(hours=4),
        closed_at=func.now() - timedelta(hours=3),
        close_reason="settled",
    )
    db_session.add(old_sitting)
    await db_session.flush()
    old_session = GuestSession(
        restaurant_id=r.id,
        table_id=table.id,
        sitting_id=old_sitting.id,
        language="en",
        expires_at=func.now() + timedelta(hours=1),
    )
    db_session.add(old_session)
    await db_session.flush()
    db_session.add(
        Order(
            guest_session_id=old_session.id,
            restaurant_id=r.id,
            table_id=table.id,
            sitting_id=old_sitting.id,
            total=Decimal("100.00"),
            idempotency_key=uuid.uuid4().hex,
            payload_hash=uuid.uuid4().hex,
            placed_at=func.now() - timedelta(hours=3, minutes=30),
        )
    )

    # Second, new sitting on the same table: opened 2 minutes ago, no orders yet.
    new_sitting = TableSitting(
        table_id=table.id,
        opened_at=func.now() - timedelta(minutes=2),
    )
    db_session.add(new_sitting)
    await db_session.flush()

    result = await get_open_sitting(db_session, table.id)

    assert result is not None
    assert result.id == new_sitting.id
    assert result.closed_at is None


async def test_an_open_unpaid_bill_is_never_idle_closed(db_session):
    """Spec §1: a sitting with an open bill stays open however long it has been quiet."""
    r = Restaurant(
        name="Unpaid Venue",
        slug=f"unpaid-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(r)
    await db_session.flush()
    table = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    db_session.add(table)
    await db_session.flush()
    sitting = TableSitting(table_id=table.id, opened_at=func.now() - timedelta(hours=3))
    db_session.add_all([sitting, Bill(restaurant_id=r.id, table_id=table.id, bill_no=1)])
    await db_session.flush()

    result = await get_open_sitting(db_session, table.id)

    assert result is not None
    assert result.id == sitting.id
    assert result.closed_at is None


async def _venue_table(db_session) -> tuple[Restaurant, DiningTable]:
    r = Restaurant(
        name="Idle Venue",
        slug=f"idle-{uuid.uuid4().hex[:8]}",
        city="Lahore",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
        tax_jurisdiction="PB",
    )
    db_session.add(r)
    await db_session.flush()
    table = DiningTable(restaurant_id=r.id, label="T1", qr_token=uuid.uuid4().hex)
    db_session.add(table)
    await db_session.flush()
    return r, table


async def test_the_previous_partys_waiter_call_does_not_idle_close_a_new_sitting(db_session):
    """A call made 2h ago (before this sitting opened 30 min ago) is not this party's activity."""
    r, table = await _venue_table(db_session)
    db_session.add(
        ServiceCall(
            restaurant_id=r.id,
            table_id=table.id,
            reason="help",
            created_at=func.now() - timedelta(hours=2),
            resolved_at=func.now() - timedelta(hours=2),
        )
    )
    sitting = TableSitting(table_id=table.id, opened_at=func.now() - timedelta(minutes=30))
    db_session.add(sitting)
    await db_session.flush()

    result = await get_open_sitting(db_session, table.id)

    assert result is not None and result.id == sitting.id
