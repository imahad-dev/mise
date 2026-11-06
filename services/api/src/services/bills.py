"""Table bills: opening under a per-restaurant lock, grouped lines, tax previews, settle."""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.schemas.bills import BillLine, MethodPreview, PaymentClaim, TaxPreview
from src.services.pay_forward import record_bought
from src.services.tax import (
    CENTS,  # noqa: F401 - routers import it from here
    TaxRateError,
    charge_for,
    default_rates,
    methods_for,
    payment_class,
    service_charge_for,
)

logger = logging.getLogger(__name__)
VISIT_ENDED = "Your visit has ended — scan the table QR again"
REUSE_WINDOW = timedelta(days=7)
EXPIRED = "Expired unpaid"


class BillChanged(Exception):  # noqa: N818 - a signal, not an error
    """The staff member's expected total no longer matches the server's recomputation."""


def _reset_at(table_id: uuid.UUID):
    """When the table last reset: cleared, or one of its bills settled or cancelled."""
    return select(DiningTable.reset_at).where(DiningTable.id == table_id).scalar_subquery()


async def mark_table_reset(
    db: AsyncSession, table_id: uuid.UUID, at: datetime | None = None
) -> None:
    """Stamp a reset (clear, settle, a bill cancelled by voids, a closed table) on a table. The
    database clock can step back, so the stamp is also after the last reset and after every
    phone that scanned (session_started_at may stamp those ahead of the clock): only those that
    scan from now on are current. Caller commits.

    `at` stamps a reset that happened earlier (an idle close found later): phones that scanned
    after it belong to the next party and stay current."""
    one = timedelta(microseconds=1)
    last_scan = (
        select(func.max(GuestSession.created_at))
        .where(GuestSession.table_id == table_id)
        .scalar_subquery()
    )
    # greatest() skips NULLs: a table never reset, or never scanned.
    stamp = (
        func.greatest(at, DiningTable.reset_at + one)
        if at is not None
        else func.greatest(func.clock_timestamp(), DiningTable.reset_at + one, last_scan + one)
    )
    await db.execute(update(DiningTable).where(DiningTable.id == table_id).values(reset_at=stamp))


async def session_started_at(db: AsyncSession, table_id: uuid.UUID) -> datetime:
    """created_at for a new session at the table: the database clock, but always after the
    table's last reset. The wall clock can step back (time sync), and a phone that scans after a
    settle must never look like it scanned before it (session_is_current)."""
    return await db.scalar(
        select(
            func.greatest(func.clock_timestamp(), _reset_at(table_id) + timedelta(microseconds=1))
        )
    )


async def session_is_current(db: AsyncSession, session: GuestSession) -> bool:
    """Whether a table session still belongs to the party at the table.

    The table resets when it is cleared or one of its bills is settled or cancelled (every order
    voided). A session is current if
    it began after the last reset, or it has an active order on the table's open bill.
    A counter session is always current: each of its orders opens its own bill.
    """
    if session.table_id is None:
        return True
    kind = await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
    if kind == "counter":
        return True
    reset = await db.scalar(select(_reset_at(session.table_id)))
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


async def lock_open_bill(
    db: AsyncSession, restaurant_id: uuid.UUID, table_id: uuid.UUID
) -> Bill | None:
    """The table's open bill locked FOR UPDATE (None if there is none), under the restaurant's
    bill lock. Take it before the table's sitting lock: bill first, then sitting, everywhere."""
    # Serialises bill numbering per restaurant. A concurrent settle holds the bill row lock;
    # FOR UPDATE re-checks status once it commits, so a settled bill is skipped here.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant_id}"))))
    return (
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


async def open_bill_for_table(
    db: AsyncSession, restaurant_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[Bill, bool]:
    """(The table's open bill locked FOR UPDATE, or a new one; created?). Caller owns the txn."""
    bill = await lock_open_bill(db, restaurant_id, table_id)
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


async def active_orders(
    db: AsyncSession, bill_id: uuid.UUID, *, include_expired: bool = False
) -> list[Order]:
    """The bill's non-cancelled orders with items loaded.

    include_expired: the orders an expired counter bill would get back (every unvoided one).
    """
    alive = Order.voided_at.is_(None) if include_expired else Order.status != "cancelled"
    return list(
        (
            await db.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.bill_id == bill_id, alive)
                .order_by(Order.placed_at, Order.id)
            )
        )
        .scalars()
        .all()
    )


def is_expired_unpaid(bill: Bill) -> bool:
    """Cancelled by the 30-minute expiry, not by staff or voids: money may still arrive."""
    return (
        bill.status == "cancelled" and bill.cancel_reason == EXPIRED and bill.cancelled_by is None
    )


async def revive_expired(
    db: AsyncSession, bill: Bill, restaurant_id: uuid.UUID, actor: str
) -> list[uuid.UUID]:
    """Reopen an expired counter bill (caller holds its lock); returns the revived order ids."""
    bill.status = "open"
    bill.cancelled_at = None
    bill.cancelled_by = None
    bill.cancel_reason = None
    revived = list(
        (
            await db.execute(
                update(Order)
                .where(
                    Order.bill_id == bill.id,
                    Order.status == "cancelled",
                    Order.voided_at.is_(None),
                )
                .values(status="awaiting_payment")
                .returning(Order.id)
            )
        )
        .scalars()
        .all()
    )
    db.add(
        AuditLog(
            restaurant_id=restaurant_id,
            event_type="bill_revived",
            actor=actor,
            payload={"bill_id": str(bill.id), "order_ids": [str(i) for i in revived]},
        )
    )
    await db.flush()
    return revived


def bill_lines(orders: list[Order]) -> tuple[list[BillLine], Decimal]:
    """Lines grouped by (dish, option, unit price, choices), sorted by dish then price; subtotal."""
    qty: dict[tuple, int] = {}
    chosen: dict[tuple, list[dict]] = {}
    for order in orders:
        for oi in order.items:
            # Sorted: reordering groups mid-visit must not split identical choices.
            names = tuple(sorted(f"{c['group']}: {c['label']}" for c in oi.choices))
            key = (oi.item_name, oi.option_label, oi.unit_price, names)
            qty[key] = qty.get(key, 0) + oi.quantity
            chosen[key] = oi.choices
    # Sorted, not first-seen: orders of one transaction share placed_at, so arrival order
    # is not recoverable from the database.
    lines = [
        BillLine(
            name=key[0],
            option_label=key[1],
            quantity=q,
            unit_price=key[2],
            line_total=key[2] * Decimal(q),
            choices=chosen[key],
        )
        for key, q in sorted(
            qty.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1] or "", kv[0][3])
        )
    ]
    return lines, sum((line.line_total for line in lines), Decimal("0.00"))


def _preview(
    jurisdiction: str | None, method: str, subtotal: Decimal, on_date: date
) -> TaxPreview | None:
    try:
        c = charge_for(jurisdiction or "", method, on_date, subtotal, default_rates())
    except TaxRateError:
        return None
    return TaxPreview(
        payment_class=payment_class(method),
        tax_rate=c.rate,
        tax_amount=c.tax,
        total=c.total,
        tax_included=c.pricing == "included",
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
    """Tax and total for each method the venue accepts; methods without a rate are left out."""
    out = [method_preview(jurisdiction, m, subtotal, on_date) for m in methods_for(jurisdiction)]
    return [p for p in out if p is not None]


def bill_service(restaurant: Restaurant, bill: Bill, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """The optional service charge this bill would carry: table bills only."""
    return service_charge_for(
        restaurant.tax_jurisdiction,
        restaurant.service_charge_rate,
        subtotal,
        bill.table_id is not None,
    )


METHOD_REFUSED = "Payment method not accepted here"


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
        service_included=bill.claimed_service_included,
    )


# One key for a payment reference, everywhere: "TX 1", "tx-1", "TX_1" and "TX1" are one payment.
_REF_SEPARATORS = " -./#_"


def reference_key(reference: str | None) -> str:
    return "".join(c for c in (reference or "") if c not in _REF_SEPARATORS).upper()


def _reference_key_sql(column):
    """reference_key() in SQL: translate() drops the separator characters."""
    return func.upper(func.translate(column, _REF_SEPARATORS, ""))


async def reused_reference_bill_no(
    db: AsyncSession, restaurant_id: uuid.UUID, bill_id: uuid.UUID, keys: list[str]
) -> int | None:
    """Another settled or cancelled bill of this venue (last 7 days) whose reference or claim
    has a key. A cancelled bill keeps its guest's claim, so the same money is not taken twice."""
    keys = [k for k in keys if k]
    if not keys:
        return None
    closed_at = func.coalesce(Bill.settled_at, Bill.cancelled_at)
    return await db.scalar(
        select(Bill.bill_no)
        .where(
            Bill.restaurant_id == restaurant_id,
            Bill.id != bill_id,
            Bill.status.in_(("settled", "cancelled")),
            closed_at > func.clock_timestamp() - REUSE_WINDOW,
            _reference_key_sql(Bill.payment_reference).in_(keys)
            | _reference_key_sql(Bill.claimed_reference).in_(keys),
        )
        .order_by(closed_at.desc())
        .limit(1)
    )


async def open_bill_with_claimed_key(
    db: AsyncSession, restaurant_id: uuid.UUID, bill_id: uuid.UUID, key: str
) -> int | None:
    """Another open bill of this venue whose guest claimed the same reference."""
    if not key:
        return None
    return await db.scalar(
        select(Bill.bill_no)
        .where(
            Bill.restaurant_id == restaurant_id,
            Bill.id != bill_id,
            Bill.status == "open",
            _reference_key_sql(Bill.claimed_reference) == key,
        )
        .order_by(Bill.opened_at)
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
    service_included: bool = False,
    acknowledge_service_change: bool = False,
) -> tuple[Bill, list[uuid.UUID], list[uuid.UUID]]:
    """Lock the bill, recompute, check the staff's expectation, snapshot tax. Caller commits.

    Returns the bill, the ids of counter orders released to the kitchen (awaiting_payment
    -> placed) and of orders revived from an expired counter bill; the caller publishes
    order_revived / order_placed for them after commit. An expired (unpaid) counter bill is
    reopened first: money that arrives late is still taken.
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
    expired = is_expired_unpaid(bill)
    if bill.status != "open" and not expired:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
    # Database clock (same as orders.placed_at), read after the lock: every order on this
    # bill committed before it.
    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    # Nothing is modified before the expected-total check, so BillChanged leaves no trace.
    if method not in methods_for(restaurant.tax_jurisdiction):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=METHOD_REFUSED
        )
    orders = await active_orders(db, bill.id, include_expired=expired)
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No active orders"
        )
    _, subtotal = bill_lines(orders)
    try:
        c = charge_for(
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
    sc_rate, sc_amount = bill_service(restaurant, bill, subtotal)
    service_offered = sc_amount > 0  # as the staff screen decides: a 0.00 service is none
    if not service_included:
        sc_rate, sc_amount = Decimal("0.0000"), Decimal("0.00")
    if c.total + sc_amount != expected_total:
        raise BillChanged
    # Both the staff's reference and the guest's claimed one. Per-reference locks (sorted, so
    # no cycle) serialise two bills settling with the same reference: the second sees the first.
    keys = sorted(
        {k for k in (reference_key(reference), reference_key(bill.claimed_reference)) if k}
    )
    for key in keys:
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"ref:{restaurant.id}:{key}")))
        )
    reused = await reused_reference_bill_no(db, restaurant.id, bill.id, keys)
    for key in keys:
        if reused is None:
            reused = await open_bill_with_claimed_key(db, restaurant.id, bill.id, key)
    if reused is not None and not acknowledge_reused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reference already used on {bill_no_label(reused)}",
        )
    # Staff may change the guest's service choice, but never silently.
    if (
        claim_of(bill) is not None
        and service_offered
        and service_included != bill.claimed_service_included
        and not acknowledge_service_change
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Service choice differs from the guest's",
        )
    revived = await revive_expired(db, bill, restaurant.id, f"user:{user_id}") if expired else []
    bill.status = "settled"
    bill.payment_method = method
    bill.payment_reference = reference
    bill.subtotal = subtotal
    bill.tax_jurisdiction = restaurant.tax_jurisdiction
    bill.tax_rate = c.rate
    bill.tax_amount = c.tax
    bill.tax_pricing = c.pricing
    bill.service_charge_rate = sc_rate
    bill.service_charge_amount = sc_amount
    bill.total = c.total + sc_amount
    bill.settled_at = now
    bill.settled_by = user_id
    # Under the bill lock, so no other path can change these orders meanwhile.
    released = list(
        (
            await db.execute(
                update(Order)
                .where(Order.bill_id == bill.id, Order.status == "awaiting_payment")
                .values(status="placed")
                .returning(Order.id)
            )
        )
        .scalars()
        .all()
    )
    await record_bought(db, restaurant.id, orders)
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
    return bill, released, revived
