"""Bills for staff and owners: list, detail with tax previews, settle, void an order; counter
pickup cancel, collect and undo."""

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

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
    CancelBillRequest,
    CollectResponse,
    SettleBillRequest,
    VoidOrderRequest,
)
from src.services.bills import (
    CENTS,
    EXPIRED,
    METHOD_LABELS,
    BillChanged,
    active_orders,
    bill_lines,
    claim_of,
    is_expired_unpaid,
    local_date,
    method_previews,
    open_bill_with_claimed_key,
    previews,
    reference_key,
    reused_reference_bill_no,
    settle_bill,
)
from src.services.counter import (
    UNDO_COLLECT,
    expire_unpaid,
    order_status,
    pickup_label,
    pickup_today,
)

# Prefix stops at the venue so the void route can share it; bill paths are unchanged.
router = APIRouter(prefix="/api/restaurants/{slug}", tags=["bills"])

RESPONSES = {
    401: {"description": "Unauthenticated"},
    404: {"description": "Restaurant or bill not found"},
}
JOINED_LATE = timedelta(minutes=20)
ALL_VOIDED = "All orders voided"
CANCELLED_BY_STAFF = "Cancelled by staff"


async def _order_cancelled(order_id: uuid.UUID) -> None:
    """Tell the guest following this order that it will not be made."""
    await publish_event(
        f"orders:{order_id}", json.dumps({"event": "order_cancelled", "order_id": str(order_id)})
    )


async def counter_fields(
    db: AsyncSession, restaurant: Restaurant, bills: list[Bill]
) -> dict[uuid.UUID, dict]:
    """Pickup label, the single order's id and status, and the yesterday tag per counter bill."""
    counter = [b for b in bills if b.pickup_no is not None]
    if not counter:
        return {}
    today = pickup_today(restaurant, await db.scalar(select(func.clock_timestamp())))
    rows = (
        await db.execute(
            select(Order.bill_id, Order.id, Order.status, Order.collected_at).where(
                Order.bill_id.in_([b.id for b in counter])
            )
        )
    ).all()
    by_bill = {r.bill_id: r for r in rows}
    out = {}
    for b in counter:
        r = by_bill.get(b.id)
        out[b.id] = {
            "pickup_label": pickup_label(restaurant.pickup_prefix, b.pickup_no),
            "order_id": r.id if r else None,
            "order_status": order_status(r.status, r.collected_at) if r else None,
            "collected_at": r.collected_at if r else None,
            "pickup_yesterday": b.pickup_day < today,
        }
    return out


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
    # An expired counter bill shows what settling it would take (its unvoided orders).
    expired = is_expired_unpaid(bill)
    orders = [o for o in every if (o.voided_at is None if expired else o.status != "cancelled")]
    lines, live_subtotal = bill_lines(orders)
    # A settled bill shows its snapshot; the running total applies only while open.
    subtotal = bill.subtotal if bill.status == "settled" else live_subtotal
    label = (
        await db.scalar(select(DiningTable.label).where(DiningTable.id == bill.table_id))
        if bill.table_id
        else None
    )
    # Database clock, as settle uses: the preview date is the date settle would tax at.
    at = bill.settled_at or await db.scalar(select(func.clock_timestamp()))
    on_date = local_date(restaurant, at)
    standard, digital = previews(restaurant.tax_jurisdiction, subtotal, on_date)
    methods = method_previews(restaurant.tax_jurisdiction, subtotal, on_date)
    claim = claim_of(bill)
    due = reused = reused_open = None
    if claim is not None and bill.status == "open":
        current = next((m for m in methods if m.method == claim.method), None)
        due = None if current is None else current.total - claim.total
        key = reference_key(claim.reference)
        reused = await reused_reference_bill_no(db, restaurant.id, bill.id, [key])
        reused_open = await open_bill_with_claimed_key(db, restaurant.id, bill.id, key)
    names = dict(
        (
            await db.execute(
                select(User.id, User.name).where(User.id.in_([bill.settled_by, bill.cancelled_by]))
            )
        ).all()
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
        methods=methods,
        claim=claim,
        amount_due_after_claim=due,
        reused_reference_bill_no=reused,
        reused_reference_open_bill_no=reused_open,
        orders=bill_orders(bill, every),
        settled_by_name=names.get(bill.settled_by),
        cancelled_by_name=names.get(bill.cancelled_by),
        cancelled_at=bill.cancelled_at,
        cancel_reason=bill.cancel_reason,
        **(await counter_fields(db, restaurant, [bill])).get(bill.id, {}),
    )


@router.get("/bills", response_model=BillListResponse, responses=RESPONSES)
async def list_bills(
    status_filter: Literal["open", "settled", "cancelled"] = Query("open", alias="status"),
    kind: Literal["table", "counter"] | None = Query(None),
    queue: bool = Query(False),
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillListResponse:
    """Open bills (requested first, then oldest), or the 50 latest settled or cancelled.

    Reading open bills (other than kind=table) first cancels unclaimed counter bills left
    unpaid for 30 minutes. `status=settled&kind=counter&queue=true` lists the counter queue
    instead: every paid order from today or yesterday still preparing or ready, or collected
    within the undo window, oldest payment first.
    """
    if queue and (status_filter != "settled" or kind != "counter"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="queue=true needs status=settled&kind=counter",
        )
    rid = access.restaurant.id
    if status_filter == "open" and kind != "table":
        expired = await expire_unpaid(db, access.restaurant)
        await db.commit()
        for bill_id, order_ids in expired.items():
            await publish_event(
                f"kitchen:{rid}", json.dumps({"event": "bill_cancelled", "bill_id": str(bill_id)})
            )
            for order_id in order_ids:
                await _order_cancelled(order_id)
    stmt = (
        select(
            Bill,
            DiningTable.label,
            func.count(Order.id),
            func.sum(Order.total),
        )
        .outerjoin(DiningTable, DiningTable.id == Bill.table_id)
        .outerjoin(
            Order,
            and_(
                Order.bill_id == Bill.id,
                or_(
                    Order.status != "cancelled",
                    # is_expired_unpaid in SQL: such a bill still shows its real total.
                    and_(
                        Bill.status == "cancelled",
                        Bill.cancel_reason == EXPIRED,
                        Bill.cancelled_by.is_(None),
                        Order.voided_at.is_(None),
                    ),
                ),
            ),
        )
        .where(Bill.restaurant_id == rid, Bill.status == status_filter)
        .group_by(Bill.id, DiningTable.label)
    )
    if kind == "table":
        stmt = stmt.where(Bill.pickup_no.is_(None))
    elif kind == "counter":
        stmt = stmt.where(Bill.pickup_no.is_not(None))
    if queue:
        now = await db.scalar(select(func.clock_timestamp()))
        queued = aliased(Order)
        stmt = stmt.where(
            Bill.pickup_day >= pickup_today(access.restaurant, now) - timedelta(days=1),
            exists().where(
                queued.bill_id == Bill.id,
                queued.status.in_(("placed", "bumped")),
                or_(queued.collected_at.is_(None), queued.collected_at > now - UNDO_COLLECT),
            ),
        ).order_by(Bill.settled_at, Bill.id)
    elif status_filter == "open":
        stmt = stmt.order_by(Bill.bill_requested_at.is_(None), Bill.opened_at)
    elif status_filter == "settled":
        stmt = stmt.order_by(Bill.settled_at.desc()).limit(50)
    else:
        stmt = stmt.order_by(Bill.cancelled_at.desc()).limit(50)
    rows = (await db.execute(stmt)).all()
    counter = await counter_fields(db, access.restaurant, [row[0] for row in rows])
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
                claim=claim_of(bill),
                cancelled_at=bill.cancelled_at,
                cancel_reason=bill.cancel_reason,
                **counter.get(bill.id, {}),
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
        bill, released, revived = await settle_bill(
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
    for order_id in revived:
        await publish_event(
            f"orders:{order_id}", json.dumps({"event": "order_revived", "order_id": str(order_id)})
        )
    # Paid counter orders reach the kitchen now.
    for order_id in released:
        event = json.dumps({"event": "order_placed", "order_id": str(order_id)})
        await publish_event(f"kitchen:{access.restaurant.id}", event)
        await publish_event(f"orders:{order_id}", event)
    return await bill_detail(db, access.restaurant, bill)


@router.post(
    "/orders/{order_id}/void",
    response_model=BillDetail,
    responses={
        401: {"description": "Unauthenticated"},
        404: {"description": "Restaurant or order not found"},
        409: {
            "description": "Bill not open, order already cancelled or awaiting payment, or the "
            'void would cancel a bill the guest says they paid ({"detail", "claim"}; resend '
            "with acknowledge_claim)"
        },
        # A void that empties the bill cancels it ("All orders voided").
        422: {"description": "Reason must be 1-200 characters"},
    },
)
async def void_order(
    order_id: uuid.UUID,
    payload: VoidOrderRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail | JSONResponse:
    """Take a placed or bumped order off its open bill: it leaves the kitchen and the totals.

    Voiding the last active order cancels the bill, so the table's next order opens a new one.
    """
    rid = access.restaurant.id
    # Every path locks the bill before its orders: read the bill id unlocked, lock the bill,
    # then lock the order and check it is still on that bill.
    row = (
        await db.execute(
            select(Order.bill_id).where(Order.id == order_id, Order.restaurant_id == rid)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    bill_id = row.bill_id
    bill = (
        (
            await db.execute(
                select(Bill)
                .where(Bill.id == bill_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if bill_id is not None
        else None
    )
    order = (
        await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if bill is None or bill.status != "open" or order.bill_id != bill.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
    if order.status == "awaiting_payment":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Awaiting payment")
    if order.status not in ("placed", "bumped"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order already cancelled")
    empties = all(o.id == order.id for o in await active_orders(db, bill.id))
    claim = claim_of(bill)
    if empties and claim is not None and not payload.acknowledge_claim:
        # Checked before any change; commit only ends the transaction and frees the locks.
        await db.commit()
        label = METHOD_LABELS.get(claim.method, claim.method)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": f"Guest says they paid by {label} (Rs {claim.total}) — any refund "
                "happens outside Mise. Confirm to void and cancel the bill.",
                "claim": claim.model_dump(mode="json"),
            },
        )
    now = await db.scalar(select(func.clock_timestamp()))
    actor = f"user:{access.user.id}"
    order.status = "cancelled"
    order.voided_at = now
    order.voided_by = access.user.id
    order.void_reason = payload.reason
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_voided",
            actor=actor,
            payload={"order_id": str(order.id), "bill_id": str(bill.id), "reason": payload.reason},
        )
    )
    events = [{"event": "order_voided", "order_id": str(order.id), "bill_id": str(bill.id)}]
    if empties:
        bill.status = "cancelled"
        bill.cancelled_at = now
        bill.cancelled_by = access.user.id
        bill.cancel_reason = ALL_VOIDED
        db.add(
            AuditLog(
                restaurant_id=rid,
                event_type="bill_cancelled",
                actor=actor,
                payload={
                    "bill_id": str(bill.id),
                    "reason": ALL_VOIDED,
                    **(
                        {
                            "claimed_method": claim.method,
                            "claimed_total": str(claim.total),
                            "claimed_reference_last4": (claim.reference or "")[-4:] or None,
                        }
                        if claim
                        else {}
                    ),
                },
            )
        )
        events.append({"event": "bill_cancelled", "bill_id": str(bill.id)})
    await db.commit()
    for event in events:
        await publish_event(f"kitchen:{rid}", json.dumps(event))
    return await bill_detail(db, access.restaurant, bill)


@router.post(
    "/bills/{bill_id}/cancel",
    response_model=BillDetail,
    responses={
        **RESPONSES,
        409: {"description": "Not a counter bill, already settled, or not open"},
        422: {"description": "The guest says they paid: a reason (1-200 characters) is required"},
    },
)
async def cancel_bill(
    bill_id: uuid.UUID,
    payload: CancelBillRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail:
    """Cancel an unpaid counter bill and its order (the guest left). Table bills use voids."""
    rid = access.restaurant.id
    bill = (
        await db.execute(
            select(Bill)
            .where(Bill.id == bill_id, Bill.restaurant_id == rid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found")
    if bill.pickup_no is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only counter bills can be cancelled"
        )
    if bill.status == "settled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill already settled")
    if bill.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
    claim = claim_of(bill)
    if claim is not None and payload.reason is None:
        label = METHOD_LABELS.get(claim.method, claim.method)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Guest says they paid by {label} (Rs {claim.total}) — any refund happens "
            "outside Mise. Give a reason to cancel.",
        )
    reason = payload.reason or CANCELLED_BY_STAFF
    orders = (
        (
            await db.execute(
                select(Order)
                .where(Order.bill_id == bill.id, Order.status != "cancelled")
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    for order in orders:
        order.status = "cancelled"
    now = await db.scalar(select(func.clock_timestamp()))
    bill.status = "cancelled"
    bill.cancelled_at = now
    bill.cancelled_by = access.user.id
    bill.cancel_reason = reason
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="bill_cancelled",
            actor=f"user:{access.user.id}",
            payload={
                "bill_id": str(bill.id),
                "reason": reason,
                **(
                    {
                        "claimed_method": claim.method,
                        "claimed_total": str(claim.total),
                        "claimed_reference_last4": (claim.reference or "")[-4:] or None,
                    }
                    if claim
                    else {}
                ),
            },
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "bill_cancelled", "bill_id": str(bill.id)})
    )
    for order in orders:
        await _order_cancelled(order.id)
    return await bill_detail(db, access.restaurant, bill)


async def _locked_counter_order(db: AsyncSession, rid: uuid.UUID, order_id: uuid.UUID) -> Order:
    # Only the order is locked: collect never touches the bill, so lock order stays acyclic.
    order = (
        await db.execute(
            select(Order)
            .where(Order.id == order_id, Order.restaurant_id == rid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    is_counter = order.bill_id is not None and (
        await db.scalar(select(Bill.pickup_no).where(Bill.id == order.bill_id)) is not None
    )
    if not is_counter:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Not a counter pickup order"
        )
    return order


COLLECT_RESPONSES = {
    401: {"description": "Unauthenticated"},
    404: {"description": "Restaurant or order not found"},
}


@router.post(
    "/orders/{order_id}/collect",
    response_model=CollectResponse,
    responses={
        **COLLECT_RESPONSES,
        409: {"description": "Not a counter order, not ready (bumped), or already collected"},
    },
)
async def collect_order(
    order_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> CollectResponse:
    """The guest picked up a ready counter order."""
    rid = access.restaurant.id
    order = await _locked_counter_order(db, rid, order_id)
    if order.collected_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already collected")
    if order.status != "bumped":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is not ready")
    order.collected_at = await db.scalar(select(func.clock_timestamp()))
    order.collected_by = access.user.id
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_collected",
            actor=f"user:{access.user.id}",
            payload={"order_id": str(order.id)},
        )
    )
    await db.commit()
    event = json.dumps({"event": "order_collected", "order_id": str(order.id)})
    await publish_event(f"kitchen:{rid}", event)
    await publish_event(f"orders:{order.id}", event)
    return CollectResponse(
        order_id=order.id, order_status="collected", collected_at=order.collected_at
    )


@router.post(
    "/orders/{order_id}/uncollect",
    response_model=CollectResponse,
    responses={
        **COLLECT_RESPONSES,
        409: {"description": "Not a counter order, not collected, or collected over 60 s ago"},
    },
)
async def uncollect_order(
    order_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> CollectResponse:
    """Undo Collected within 60 seconds (database clock)."""
    rid = access.restaurant.id
    order = await _locked_counter_order(db, rid, order_id)
    if order.collected_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is not collected")
    now = await db.scalar(select(func.clock_timestamp()))
    if now - order.collected_at >= UNDO_COLLECT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Undo window expired (60 seconds)"
        )
    previous = order.collected_at
    order.collected_at = None
    order.collected_by = None
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="order_uncollected",
            actor=f"user:{access.user.id}",
            payload={"order_id": str(order.id), "previous_collected_at": str(previous)},
        )
    )
    await db.commit()
    event = json.dumps({"event": "order_uncollected", "order_id": str(order.id)})
    await publish_event(f"kitchen:{rid}", event)
    await publish_event(f"orders:{order.id}", event)
    return CollectResponse(order_id=order.id, order_status=order.status, collected_at=None)
