"""Counter pickup: one bill per counter order, daily pickup numbers, expiry of unpaid orders."""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.services.bills import local_date

EXPIRY = timedelta(minutes=30)
UNDO_COLLECT = timedelta(seconds=60)
EXPIRED = "Expired unpaid"


def pickup_label(prefix: str | None, no: int) -> str:
    """K-001 … K-999, then K-1000: numbers never wrap."""
    return f"{prefix or 'K'}-{no:03d}"


def pickup_today(restaurant: Restaurant, now: datetime) -> date:
    return local_date(restaurant, now)


def order_status(status: str, collected_at: datetime | None) -> str:
    """awaiting_payment, placed, bumped, collected or cancelled."""
    return "collected" if collected_at is not None else status


async def open_counter_bill(db: AsyncSession, restaurant: Restaurant) -> Bill:
    """A new bill with the next bill and pickup numbers. Caller owns the transaction."""
    # Same key as open_bill_for_table: bill numbers and pickup numbers are serialised together.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant.id}"))))
    day = pickup_today(restaurant, await db.scalar(select(func.clock_timestamp())))
    last_bill = await db.scalar(
        select(func.max(Bill.bill_no)).where(Bill.restaurant_id == restaurant.id)
    )
    last_pickup = await db.scalar(
        select(func.max(Bill.pickup_no)).where(
            Bill.restaurant_id == restaurant.id, Bill.pickup_day == day
        )
    )
    bill = Bill(
        restaurant_id=restaurant.id,
        table_id=None,
        bill_no=(last_bill or 0) + 1,
        pickup_day=day,
        pickup_no=(last_pickup or 0) + 1,
        status="open",
        source="live",
    )
    db.add(bill)
    await db.flush()
    return bill


async def expire_unpaid(db: AsyncSession, restaurant: Restaurant) -> list[uuid.UUID]:
    """Cancel unclaimed counter bills whose order has waited unpaid for 30 minutes.

    Bills are locked FOR UPDATE SKIP LOCKED (a settle or claim in progress wins), then their
    orders: bill before order, as everywhere. Returns the cancelled bill ids; caller commits.
    """
    now = await db.scalar(select(func.clock_timestamp()))
    stale = exists().where(
        Order.bill_id == Bill.id,
        Order.status == "awaiting_payment",
        Order.placed_at < now - EXPIRY,
    )
    bills = (
        (
            await db.execute(
                select(Bill)
                .where(
                    Bill.restaurant_id == restaurant.id,
                    Bill.pickup_no.is_not(None),
                    Bill.status == "open",
                    Bill.claimed_at.is_(None),
                    stale,
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    cancelled = []
    for bill in bills:
        # Re-checked on the locked row: a claim or settle that committed first keeps the bill.
        if bill.status != "open" or bill.claimed_at is not None:
            continue
        orders = (
            (
                await db.execute(
                    select(Order)
                    .where(Order.bill_id == bill.id, Order.status == "awaiting_payment")
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        for order in orders:
            order.status = "cancelled"
        bill.status = "cancelled"
        bill.cancelled_at = now
        bill.cancel_reason = EXPIRED
        db.add(
            AuditLog(
                restaurant_id=restaurant.id,
                event_type="bill_cancelled",
                actor="system",
                payload={"bill_id": str(bill.id), "reason": EXPIRED},
            )
        )
        cancelled.append(bill.id)
    await db.flush()
    return cancelled
