"""Table sittings: pure idle check and code generation, and the DB operations around them."""

import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.order import Order
from src.models.service_call import ServiceCall
from src.models.sitting import TableSitting
from src.services.bills import lock_open_bill, open_bill_for_table

IDLE_TIMEOUT = timedelta(minutes=90)


def is_idle(*, opened_at: datetime, last_activity_at: datetime | None, now: datetime) -> bool:
    """No order, call or payment activity for IDLE_TIMEOUT since the sitting opened."""
    since = last_activity_at or opened_at
    return now - since >= IDLE_TIMEOUT


def generate_code() -> str:
    """A random 4-digit code, read aloud by staff — not cryptographic, just hard to guess."""
    return f"{secrets.randbelow(10000):04d}"


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


async def get_open_sitting(
    db: AsyncSession, table_id: uuid.UUID, cancelled: list[uuid.UUID] | None = None
) -> TableSitting | None:
    """The table's open sitting, lazily closing it first if it has gone idle (never while
    the table has an open bill). An idle close cancels the sitting's waiting orders and adds
    their ids to `cancelled`: a caller that commits publishes them (publish_declined).

    Caller owns the txn.
    """
    sitting = (
        await db.execute(
            select(TableSitting)
            .where(TableSitting.table_id == table_id, TableSitting.closed_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sitting is None:
        return None
    # Spec §1: an open unpaid bill is never idle-closed.
    open_bill = await db.scalar(
        select(Bill.id).where(Bill.table_id == table_id, Bill.status == "open").limit(1)
    )
    if open_bill is not None:
        return sitting
    now = await db.scalar(select(func.clock_timestamp()))
    last_activity = await _last_activity(db, sitting.id, sitting.table_id)
    if is_idle(opened_at=sitting.opened_at, last_activity_at=last_activity, now=now):
        ids = await _close(db, sitting, "idle_timeout", now, None)
        if cancelled is not None:
            cancelled.extend(ids)
        return None
    return sitting


async def _last_activity(
    db: AsyncSession, sitting_id: uuid.UUID, table_id: uuid.UUID
) -> datetime | None:
    order_activity = await db.scalar(
        select(func.max(Order.placed_at)).where(Order.sitting_id == sitting_id)
    )
    call_activity = await db.scalar(
        select(func.max(ServiceCall.created_at)).where(ServiceCall.table_id == table_id)
    )
    candidates = [t for t in (order_activity, call_activity) if t is not None]
    return max(candidates) if candidates else None


async def close_sitting_for_table(
    db: AsyncSession,
    table_id: uuid.UUID,
    reason: str,
    now: datetime,
    user_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Close the table's open sitting, if any, cancelling its waiting orders (`user_id` is the
    staff member closing it, None for a system close). No-op for counter tables (never have
    one) and for a table with no open sitting (settle/void paths call this unconditionally —
    it's a no-op, not an error, when there's nothing to close).

    Returns the cancelled order ids; the caller commits, then publishes them
    (publish_declined)."""
    sitting = (
        await db.execute(
            select(TableSitting)
            .where(TableSitting.table_id == table_id, TableSitting.closed_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if sitting is None:
        return []
    return await _close(db, sitting, reason, now, user_id)


async def _close(
    db: AsyncSession,
    sitting: TableSitting,
    reason: str,
    now: datetime,
    user_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Close a locked sitting; its waiting orders (never on a bill) are cancelled with it."""
    sitting.closed_at = now
    sitting.close_reason = reason
    pending = await _pending(db, sitting.id)
    for order in pending:
        order.status = "cancelled"
        order.voided_at = now
        order.voided_by = user_id
        order.void_reason = TABLE_CLOSED
        order.void_kind = "table_closed"
    await db.flush()
    return [o.id for o in pending]


# An order of these statuses means a waiter has approved the sitting: later orders skip approval.
APPROVED = ("placed", "bumped")


async def has_approved_order(db: AsyncSession, sitting_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(Order.id)
            .where(Order.sitting_id == sitting_id, Order.status.in_(APPROVED))
            .limit(1)
        )
    ) is not None


async def _pending(db: AsyncSession, sitting_id: uuid.UUID) -> list[Order]:
    return list(
        (
            await db.scalars(
                select(Order)
                .where(Order.sitting_id == sitting_id, Order.status == "pending_approval")
                .order_by(Order.placed_at, Order.id)
                .with_for_update()
            )
        ).all()
    )


ORDER_CHANGED = "The order changed. Please check the table again."
ALREADY_HANDLED = "Already handled"
DECLINED = "Declined by waiter"
TABLE_CLOSED = "Table closed"


async def _waiting_as_seen(
    db: AsyncSession, sitting: TableSitting | None, order_ids: list[uuid.UUID], *done
) -> list[Order] | None:
    """The sitting's waiting orders, when they are exactly `order_ids` (what the waiter saw).

    None when every id is already handled the way `done` (filters on Order) says: a replay.
    Otherwise 409: the waiting orders changed, or they were handled another way.
    """
    pending = await _pending(db, sitting.id) if sitting else []
    if pending and {o.id for o in pending} == set(order_ids):
        return pending
    if sitting is not None:
        handled = await db.scalar(
            select(func.count(Order.id)).where(
                Order.id.in_(order_ids), Order.sitting_id == sitting.id, *done
            )
        )
        if handled == len(set(order_ids)):
            return None
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=ORDER_CHANGED if pending else ALREADY_HANDLED
    )


async def approve_pending(
    db: AsyncSession,
    restaurant_id: uuid.UUID,
    table_id: uuid.UUID,
    actor: str,
    order_ids: list[uuid.UUID],
) -> tuple[Bill | None, bool]:
    """Send the table's waiting orders to the kitchen on the table's bill, if they are the ones
    the waiter saw (`order_ids`; see _waiting_as_seen for the 409s).

    Returns (bill, bill created?); no bill on a replay. Caller commits.
    """
    await lock_open_bill(db, restaurant_id, table_id)  # bill lock before the sitting lock
    sitting = await get_open_sitting(db, table_id)
    pending = await _waiting_as_seen(db, sitting, order_ids, Order.status.in_(APPROVED))
    if pending is None:
        return None, False
    bill, created = await open_bill_for_table(db, restaurant_id, table_id)
    for order in pending:
        order.bill_id = bill.id
        order.status = "placed"
        db.add(
            AuditLog(
                restaurant_id=restaurant_id,
                event_type="order_approved",
                actor=actor,
                payload={"order_id": str(order.id), "bill_id": str(bill.id)},
            )
        )
    await db.flush()
    return bill, created


async def decline_pending(
    db: AsyncSession,
    restaurant_id: uuid.UUID,
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    order_ids: list[uuid.UUID],
) -> bool:
    """Cancel the table's waiting orders if they are the ones the waiter saw (never on a bill,
    so no money moves); the table stays open. False on a replay. Caller commits."""
    sitting = await get_open_sitting(db, table_id)
    pending = await _waiting_as_seen(
        db, sitting, order_ids, Order.status == "cancelled", Order.void_kind == "declined"
    )
    if pending is None:
        return False
    now = await db.scalar(select(func.clock_timestamp()))
    for order in pending:
        order.status = "cancelled"
        order.voided_at = now
        order.voided_by = user_id
        order.void_reason = DECLINED
        order.void_kind = "declined"
        db.add(
            AuditLog(
                restaurant_id=restaurant_id,
                event_type="order_declined",
                actor=f"user:{user_id}",
                payload={"order_id": str(order.id)},
            )
        )
    await db.flush()
    return True
