"""Table bills: opening under a per-restaurant lock, grouped lines, tax previews, settle."""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bill import Bill
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.schemas.bills import BillLine, TaxPreview
from src.services.tax import TaxRateError, default_rates, payment_class, tax_for

logger = logging.getLogger(__name__)
CENTS = Decimal("0.01")


async def open_bill_for_table(
    db: AsyncSession, restaurant_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[Bill, bool]:
    """(The table's open bill locked FOR UPDATE, or a new one; created?). Caller owns the txn."""
    # Serialises bill numbering per restaurant. A concurrent settle holds the bill row lock;
    # FOR UPDATE re-checks status once it commits, so a settled bill is skipped here.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant_id}"))))
    bill = (
        await db.execute(
            select(Bill)
            .where(
                Bill.restaurant_id == restaurant_id,
                Bill.table_id == table_id,
                Bill.status == "open",
            )
            .with_for_update()
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


async def active_orders(db: AsyncSession, bill_id: uuid.UUID) -> list[Order]:
    """The bill's non-cancelled orders with items loaded."""
    return list(
        (
            await db.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.bill_id == bill_id, Order.status != "cancelled")
                .order_by(Order.placed_at, Order.id)
            )
        )
        .scalars()
        .all()
    )


def bill_lines(orders: list[Order]) -> tuple[list[BillLine], Decimal]:
    """Lines grouped by (dish, option, unit price), sorted by dish then price; and subtotal."""
    qty: dict[tuple[str, str | None, Decimal], int] = {}
    for order in orders:
        for oi in order.items:
            key = (oi.item_name, oi.option_label, oi.unit_price)
            qty[key] = qty.get(key, 0) + oi.quantity
    # Sorted, not first-seen: orders of one transaction share placed_at, so arrival order
    # is not recoverable from the database.
    lines = [
        BillLine(
            name=name,
            option_label=label,
            quantity=q,
            unit_price=price,
            line_total=price * Decimal(q),
        )
        for (name, label, price), q in sorted(
            qty.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1] or "")
        )
    ]
    return lines, sum((line.line_total for line in lines), Decimal("0.00"))


def _preview(
    jurisdiction: str | None, method: str, subtotal: Decimal, on_date: date
) -> TaxPreview | None:
    try:
        rate, tax = tax_for(jurisdiction or "", method, on_date, subtotal, default_rates())
    except TaxRateError:
        return None
    tax = tax.quantize(CENTS)
    return TaxPreview(
        payment_class=payment_class(method),
        tax_rate=rate,
        tax_amount=tax,
        total=subtotal + tax,
    )


def previews(
    jurisdiction: str | None, subtotal: Decimal, on_date: date
) -> tuple[TaxPreview | None, TaxPreview | None]:
    """(standard, digital) tax previews; None where no rate is configured."""
    return (
        _preview(jurisdiction, "cash", subtotal, on_date),
        _preview(jurisdiction, "card", subtotal, on_date),
    )


def local_date(restaurant: Restaurant, at: datetime) -> date:
    return at.astimezone(ZoneInfo(restaurant.timezone)).date()


async def settle_bill(
    db: AsyncSession,
    bill_id: uuid.UUID,
    restaurant: Restaurant,
    method: str,
    reference: str | None,
) -> Bill:
    """Lock the bill, snapshot tax and mark it settled. Caller commits."""
    bill = (
        await db.execute(
            select(Bill)
            .where(Bill.id == bill_id, Bill.restaurant_id == restaurant.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")
    if bill.status == "settled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill already settled")
    # Database clock (same as orders.placed_at), read after the lock: every order on this
    # bill committed before it.
    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    orders = await active_orders(db, bill.id)
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No active orders"
        )
    _, subtotal = bill_lines(orders)
    try:
        rate, tax = tax_for(
            restaurant.tax_jurisdiction or "",
            method,
            local_date(restaurant, now),
            subtotal,
            default_rates(),
        )
    except TaxRateError as e:
        logger.error("Bill %s not settled: %s", bill.id, e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No tax rate configured"
        ) from e
    tax = tax.quantize(CENTS)
    bill.status = "settled"
    bill.payment_method = method
    bill.payment_reference = reference
    bill.subtotal = subtotal
    bill.tax_jurisdiction = restaurant.tax_jurisdiction
    bill.tax_rate = rate
    bill.tax_amount = tax
    bill.total = subtotal + tax
    bill.settled_at = now
    await db.flush()
    return bill
