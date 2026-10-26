"""Table bills: opening under a per-restaurant lock, grouped lines, tax previews, settle."""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.schemas.bills import BillLine, PaymentClaim, TaxPreview
from src.schemas.payments import MethodPreview
from src.services.tax import PAYMENT_METHODS, TaxRateError, default_rates, payment_class, tax_for

logger = logging.getLogger(__name__)
CENTS = Decimal("0.01")
VISIT_ENDED = "Your visit has ended — scan the table QR again"
REUSE_WINDOW = timedelta(days=7)


class BillChanged(Exception):  # noqa: N818 - a signal, not an error
    """The staff member's expected total no longer matches the server's recomputation."""


async def session_is_current(db: AsyncSession, session: GuestSession) -> bool:
    """Whether a table session still belongs to the party at the table.

    The table resets when it is cleared or one of its bills is settled. A session is current if
    it began after the last reset, or it has an active order on the table's open bill.
    """
    if session.table_id is None:
        return True
    reset = await db.scalar(
        select(
            func.greatest(
                select(DiningTable.cleared_at)
                .where(DiningTable.id == session.table_id)
                .scalar_subquery(),
                select(func.max(Bill.settled_at))
                .where(Bill.table_id == session.table_id, Bill.status == "settled")
                .scalar_subquery(),
            )
        )
    )
    if reset is None or session.created_at > reset:
        return True
    return bool(
        await db.scalar(
            select(
                exists().where(
                    Order.guest_session_id == session.id,
                    Order.status != "cancelled",
                    Order.bill_id == Bill.id,
                    Bill.table_id == session.table_id,
                    Bill.status == "open",
                )
            )
        )
    )


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


METHOD_LABELS = {
    "cash": "Cash",
    "card": "Card",
    "wallet": "JazzCash / Easypaisa",
    "raast": "Raast QR",
    "bank_transfer": "Bank transfer",
}


def method_preview(
    jurisdiction: str | None, method: str, subtotal: Decimal, on_date: date
) -> MethodPreview | None:
    p = _preview(jurisdiction, method, subtotal, on_date)
    return (
        None
        if p is None
        else MethodPreview(method=method, label=METHOD_LABELS[method], **p.model_dump())
    )


def method_previews(
    jurisdiction: str | None, subtotal: Decimal, on_date: date
) -> list[MethodPreview]:
    """Tax and total for each of the five methods; methods without a rate are left out."""
    out = [method_preview(jurisdiction, m, subtotal, on_date) for m in PAYMENT_METHODS]
    return [p for p in out if p is not None]


def local_date(restaurant: Restaurant, at: datetime) -> date:
    return at.astimezone(ZoneInfo(restaurant.timezone)).date()


def claim_of(bill: Bill) -> PaymentClaim | None:
    if bill.claimed_method is None or bill.claimed_total is None:
        return None
    return PaymentClaim(
        method=bill.claimed_method,
        reference=bill.claimed_reference,
        total=bill.claimed_total,
        claimed_at=bill.claimed_at,
    )


async def reused_reference_bill_no(
    db: AsyncSession, restaurant_id: uuid.UUID, bill_id: uuid.UUID, reference: str | None
) -> int | None:
    """Number of another settled bill of this venue (last 7 days) that used the reference."""
    ref = (reference or "").strip().upper()
    if not ref:
        return None
    return await db.scalar(
        select(Bill.bill_no)
        .where(
            Bill.restaurant_id == restaurant_id,
            Bill.id != bill_id,
            Bill.status == "settled",
            Bill.settled_at > func.clock_timestamp() - REUSE_WINDOW,
            (func.upper(func.trim(Bill.payment_reference)) == ref)
            | (func.upper(func.trim(Bill.claimed_reference)) == ref),
        )
        .order_by(Bill.settled_at.desc())
        .limit(1)
    )


def bill_no_label(n: int | None) -> str:
    return "Bill —" if n is None else f"Bill {n:04d}"


async def settle_bill(
    db: AsyncSession,
    bill_id: uuid.UUID,
    restaurant: Restaurant,
    method: str,
    reference: str | None,
    expected_total: Decimal,
    user_id: uuid.UUID,
    acknowledge_reused: bool = False,
) -> Bill:
    """Lock the bill, recompute, check the staff's expectation, snapshot tax. Caller commits.

    Raises BillChanged (bill still locked, nothing modified) when expected_total differs.
    """
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
    if bill.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
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
    if subtotal + tax != expected_total:
        raise BillChanged
    reused = await reused_reference_bill_no(db, restaurant.id, bill.id, reference)
    if reused is not None and not acknowledge_reused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reference already used on {bill_no_label(reused)}",
        )
    bill.status = "settled"
    bill.payment_method = method
    bill.payment_reference = reference
    bill.subtotal = subtotal
    bill.tax_jurisdiction = restaurant.tax_jurisdiction
    bill.tax_rate = rate
    bill.tax_amount = tax
    bill.total = subtotal + tax
    bill.settled_at = now
    bill.settled_by = user_id
    db.add(
        AuditLog(
            restaurant_id=restaurant.id,
            event_type="bill_settled",
            actor=f"user:{user_id}",
            payload={
                "bill_id": str(bill.id),
                "method": method,
                "total": str(bill.total),
                "reused_reference_bill_no": reused,
            },
        )
    )
    await db.flush()
    return bill
