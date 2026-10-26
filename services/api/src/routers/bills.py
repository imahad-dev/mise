"""Table bills for staff and owners: list, detail with tax previews, settle, void an order."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, member_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.models.user import User
from src.redis_client import publish_event
from src.schemas.bills import (
    BillDetail,
    BillListResponse,
    BillOrder,
    BillSummary,
    SettleBillRequest,
    VoidOrderRequest,
)
from src.services.bills import (
    CENTS,
    BillChanged,
    bill_lines,
    claim_of,
    local_date,
    method_preview,
    previews,
    reused_reference_bill_no,
    settle_bill,
)

# Prefix stops at the venue so the void route can share it; bill paths are unchanged.
router = APIRouter(prefix="/api/restaurants/{slug}", tags=["bills"])

RESPONSES = {
    401: {"description": "Unauthenticated"},
    404: {"description": "Restaurant or bill not found"},
}
JOINED_LATE = timedelta(minutes=20)


def bill_orders(bill: Bill, orders: list[Order]) -> list[BillOrder]:
    """Every order on the bill, voided too, with a device label per guest session.

    orders are sorted by (placed_at, id); sessions are numbered by their first order, voided
    orders included, so labels never shift after a void.
    """
    first: dict[uuid.UUID, datetime] = {}
    for o in orders:
        first.setdefault(o.guest_session_id, o.placed_at)
    phone = {sid: n for n, sid in enumerate(first, start=1)}
    return [
        BillOrder(
            order_id=o.id,
            placed_at=o.placed_at,
            status=o.status,
            device_label=f"Phone {phone[o.guest_session_id]}",
            joined_late=phone[o.guest_session_id] != 1
            and first[o.guest_session_id] - bill.opened_at > JOINED_LATE,
            voided=o.voided_at is not None,
            void_reason=o.void_reason,
            lines=bill_lines([o])[0],
        )
        for o in orders
    ]


async def bill_detail(db: AsyncSession, restaurant: Restaurant, bill: Bill) -> BillDetail:
    every = list(
        (
            await db.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.bill_id == bill.id)
                .order_by(Order.placed_at, Order.id)
            )
        )
        .scalars()
        .all()
    )
    orders = [o for o in every if o.status != "cancelled"]
    lines, live_subtotal = bill_lines(orders)
    # A settled bill shows its snapshot; the running total applies only while open.
    subtotal = bill.subtotal if bill.status == "settled" else live_subtotal
    label = (
        await db.scalar(select(DiningTable.label).where(DiningTable.id == bill.table_id))
        if bill.table_id
        else None
    )
    on_date = local_date(restaurant, bill.settled_at or datetime.now(UTC))
    standard, digital = previews(restaurant.tax_jurisdiction, subtotal, on_date)
    claim = claim_of(bill)
    due = reused = None
    if claim is not None and bill.status == "open":
        current = method_preview(restaurant.tax_jurisdiction, claim.method, subtotal, on_date)
        due = None if current is None else current.total - claim.total
        reused = await reused_reference_bill_no(db, restaurant.id, bill.id, claim.reference)
    settled_by_name = (
        await db.scalar(select(User.name).where(User.id == bill.settled_by))
        if bill.settled_by
        else None
    )
    return BillDetail(
        id=bill.id,
        bill_no=bill.bill_no,
        table_label=label,
        status=bill.status,
        opened_at=bill.opened_at,
        order_count=len(orders),
        subtotal=subtotal,
        bill_requested_at=bill.bill_requested_at,
        lines=lines,
        preview_standard=standard,
        preview_digital=digital,
        payment_method=bill.payment_method,
        payment_reference=bill.payment_reference,
        tax_jurisdiction=bill.tax_jurisdiction,
        tax_rate=bill.tax_rate,
        tax_amount=bill.tax_amount,
        total=bill.total,
        settled_at=bill.settled_at,
        restaurant_name=restaurant.name,
        restaurant_city=restaurant.city,
        restaurant_timezone=restaurant.timezone,
        currency=restaurant.currency,
        claim=claim,
        amount_due_after_claim=due,
        reused_reference_bill_no=reused,
        orders=bill_orders(bill, every),
        settled_by_name=settled_by_name,
    )


@router.get("/bills", response_model=BillListResponse, responses=RESPONSES)
async def list_bills(
    status_filter: Literal["open", "settled"] = Query("open", alias="status"),
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillListResponse:
    """Open bills (requested first, then oldest) or the 50 latest settled bills."""
    stmt = (
        select(
            Bill,
            DiningTable.label,
            func.count(Order.id),
            func.sum(Order.total),
        )
        .outerjoin(DiningTable, DiningTable.id == Bill.table_id)
        .outerjoin(Order, and_(Order.bill_id == Bill.id, Order.status != "cancelled"))
        .where(Bill.restaurant_id == access.restaurant.id, Bill.status == status_filter)
        .group_by(Bill.id, DiningTable.label)
    )
    if status_filter == "open":
        stmt = stmt.order_by(Bill.bill_requested_at.is_(None), Bill.opened_at)
    else:
        stmt = stmt.order_by(Bill.settled_at.desc()).limit(50)
    rows = (await db.execute(stmt)).all()
    return BillListResponse(
        restaurant_timezone=access.restaurant.timezone,
        bills=[
            BillSummary(
                id=bill.id,
                bill_no=bill.bill_no,
                table_label=label,
                status=bill.status,
                opened_at=bill.opened_at,
                order_count=count,
                subtotal=(
                    bill.subtotal
                    if bill.status == "settled"
                    else (subtotal or Decimal("0")).quantize(CENTS)
                ),
                bill_requested_at=bill.bill_requested_at,
            )
            for bill, label, count, subtotal in rows
        ],
    )


@router.get("/bills/{bill_id}", response_model=BillDetail, responses=RESPONSES)
async def get_bill(
    bill_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail:
    bill = (
        await db.execute(
            select(Bill).where(Bill.id == bill_id, Bill.restaurant_id == access.restaurant.id)
        )
    ).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")
    return await bill_detail(db, access.restaurant, bill)


@router.post(
    "/bills/{bill_id}/settle",
    response_model=BillDetail,
    responses={
        **RESPONSES,
        409: {
            "description": "Bill already settled or not open; reference already used on another "
            'bill; or {"detail": "Bill changed", "bill": <fresh BillDetail>}'
        },
        422: {"description": "No active orders, no tax rate, or expected_method mismatch"},
    },
)
async def settle(
    bill_id: uuid.UUID,
    payload: SettleBillRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail | JSONResponse:
    try:
        bill = await settle_bill(
            db,
            bill_id,
            access.restaurant,
            payload.payment_method,
            payload.payment_reference,
            payload.expected_total,
            access.user.id,
            payload.acknowledge_reused_reference,
        )
    except BillChanged:
        # Still under the bill lock and unmodified: the fresh detail matches what settle saw.
        # Commit (nothing changed) rather than roll back, which would expire loaded objects.
        bill = await db.get(Bill, bill_id)
        fresh = await bill_detail(db, access.restaurant, bill)
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Bill changed", "bill": fresh.model_dump(mode="json")},
        )
    await db.commit()
    await publish_event(
        f"kitchen:{access.restaurant.id}",
        json.dumps({"event": "bill_settled", "bill_id": str(bill.id)}),
    )
    return await bill_detail(db, access.restaurant, bill)


@router.post(
    "/orders/{order_id}/void",
    response_model=BillDetail,
    responses={
        401: {"description": "Unauthenticated"},
        404: {"description": "Restaurant or order not found"},
        409: {"description": "Bill not open, or the order is already cancelled"},
        422: {"description": "Reason must be 1-200 characters"},
    },
)
async def void_order(
    order_id: uuid.UUID,
    payload: VoidOrderRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail:
    """Take a placed or bumped order off its open bill: it leaves the kitchen and the totals."""
    rid = access.restaurant.id
    # Order, then bill. Settle and order placement lock only the bill, so no lock cycle.
    order = (
        await db.execute(
            select(Order).where(Order.id == order_id, Order.restaurant_id == rid).with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    bill = None
    if order.bill_id is not None:
        bill = (
            await db.execute(select(Bill).where(Bill.id == order.bill_id).with_for_update())
        ).scalar_one()
    if bill is None or bill.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
    if order.status not in ("placed", "bumped"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order already cancelled")
    order.status = "cancelled"
    order.voided_at = await db.scalar(select(func.clock_timestamp()))
    order.voided_by = access.user.id
    order.void_reason = payload.reason
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_voided",
            actor=f"user:{access.user.id}",
            payload={"order_id": str(order.id), "bill_id": str(bill.id), "reason": payload.reason},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}",
        json.dumps({"event": "order_voided", "order_id": str(order.id), "bill_id": str(bill.id)}),
    )
    return await bill_detail(db, access.restaurant, bill)
