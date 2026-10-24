"""Table bills: opening under a per-restaurant lock."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill


async def open_bill_for_table(
    db: AsyncSession, restaurant_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[Bill, bool]:
    """(The table's open bill locked FOR UPDATE, or a new one; created?). Caller owns the txn."""
    # Serialises bill numbering per restaurant. A concurrent settle holds the bill row lock;
    # FOR UPDATE re-checks status once it commits, so a settled bill is skipped here.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant_id}"))))
    bill = (
        await db.execute(
            select(Bill).where(Bill.table_id == table_id, Bill.status == "open").with_for_update()
        )
    ).scalar_one_or_none()
    if bill is not None:
        return bill, False
    last = (
        await db.execute(select(func.max(Bill.bill_no)).where(Bill.restaurant_id == restaurant_id))
    ).scalar_one()
    bill = Bill(
        restaurant_id=restaurant_id,
        table_id=table_id,
        bill_no=(last or 0) + 1,
        status="open",
        source="live",
    )
    db.add(bill)
    await db.flush()
    return bill, True
