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
    """The table's open sitting, lazily closing it first if it has gone idle.

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
    now = await db.scalar(select(func.clock_timestamp()))
    last_activity = await _last_activity(db, sitting.id, sitting.table_id)
    if is_idle(opened_at=sitting.opened_at, last_activity_at=last_activity, now=now):
        sitting.closed_at = now
        sitting.close_reason = "idle_timeout"
        await db.flush()
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
    db: AsyncSession, table_id: uuid.UUID, reason: str, now: datetime
) -> None:
    """Close the table's open sitting, if any. No-op for counter tables (never have one) and
    for a table with no open sitting (settle/void paths call this unconditionally — it's a
    no-op, not an error, when there's nothing to close). Caller owns the txn."""
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
