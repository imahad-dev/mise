"""Floor view for staff: table tiles with timing levels, clearing, resolving waiter calls."""

import json
import re
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, member_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.service_call import ServiceCall
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.redis_client import publish_declined, publish_event
from src.schemas.floor import (
    ApprovalRequest,
    ApprovalResponse,
    ClearTableRequest,
    CloseSittingResponse,
    FloorResponse,
    FloorTile,
    GiveRequest,
    GiveResponse,
    OpenSittingResponse,
    ServiceCallResponse,
    TableClearedResponse,
    call_response,
)
from src.services import pay_forward
from src.services.bills import CENTS, lock_open_bill, mark_table_reset
from src.services.floor import THRESHOLDS, TableFacts, reason_label, table_state
from src.services.sitting import (
    approve_pending,
    close_sitting_for_table,
    decline_pending,
    get_open_sitting,
    open_sitting_for_table,
)

router = APIRouter(prefix="/api/restaurants/{slug}", tags=["floor"])

RESPONSES = {
    401: {"description": "Unauthenticated"},
    404: {"description": "Restaurant, table or call not found"},
}
LEVEL_ORDER = {"red": 0, "amber": 1, "none": 2}


def _natural(label: str) -> list:
    """T2 sorts before T10."""
    # Odd pieces of the split are the [0-9] runs, so int() never sees "²" or other digits.
    return [
        (0, int(p), "") if i % 2 else (1, 0, p.lower())
        for i, p in enumerate(re.split(r"([0-9]+)", label))
    ]


@router.get("/floor", response_model=FloorResponse, responses=RESPONSES)
async def get_floor(
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> FloorResponse:
    """One tile per table (counters excluded): red first, then amber, then label order."""
    rid = access.restaurant.id
    now = await db.scalar(select(func.clock_timestamp()))
    tables = (await db.scalars(select(DiningTable).where(DiningTable.restaurant_id == rid))).all()
    last_session = dict(
        (
            await db.execute(
                select(GuestSession.table_id, func.max(GuestSession.created_at))
                .where(GuestSession.restaurant_id == rid, GuestSession.table_id.is_not(None))
                .group_by(GuestSession.table_id)
            )
        ).all()
    )
    open_bills = {
        row.table_id: row
        for row in (
            await db.execute(
                select(
                    Bill.table_id,
                    Bill.id,
                    Bill.bill_requested_at,
                    func.min(Order.placed_at).filter(Order.status == "placed").label("oldest"),
                    func.count(Order.id).label("active"),
                    func.sum(Order.total).label("total"),
                )
                .outerjoin(Order, and_(Order.bill_id == Bill.id, Order.status != "cancelled"))
                .where(Bill.restaurant_id == rid, Bill.status == "open", Bill.table_id.is_not(None))
                .group_by(Bill.id)
            )
        ).all()
    }
    last_settled = dict(
        (
            await db.execute(
                select(Bill.table_id, func.max(Bill.settled_at))
                .where(Bill.restaurant_id == rid, Bill.status == "settled")
                .group_by(Bill.table_id)
            )
        ).all()
    )
    last_cancelled = dict(
        (
            await db.execute(
                select(Bill.table_id, func.max(Bill.cancelled_at))
                .where(Bill.restaurant_id == rid, Bill.status == "cancelled")
                .group_by(Bill.table_id)
            )
        ).all()
    )
    calls = {
        c.table_id: c
        for c in (
            await db.scalars(
                select(ServiceCall).where(
                    ServiceCall.restaurant_id == rid, ServiceCall.resolved_at.is_(None)
                )
            )
        ).all()
    }
    sittings = {
        s.table_id: s
        for s in (
            await db.scalars(
                select(TableSitting).where(
                    TableSitting.table_id.in_([t.id for t in tables]),
                    TableSitting.closed_at.is_(None),
                )
            )
        ).all()
    }
    # Every waiting order of each open sitting, oldest first: the waiter approves them together.
    pending: dict[uuid.UUID, list[Order]] = {}
    for o in (
        await db.scalars(
            select(Order)
            .join(TableSitting, TableSitting.id == Order.sitting_id)
            .options(selectinload(Order.items))
            .where(
                Order.restaurant_id == rid,
                Order.status == "pending_approval",
                TableSitting.closed_at.is_(None),
            )
            .order_by(Order.placed_at, Order.id)
        )
    ).all():
        pending.setdefault(o.table_id, []).append(o)

    extra = access.restaurant.service_extra_label
    tiles: list[FloorTile] = []
    for t in tables:
        bill = open_bills.get(t.id)
        call = calls.get(t.id)
        total = (bill.total or Decimal("0")).quantize(CENTS) if bill else None
        sitting = sittings.get(t.id)
        pend = pending.get(t.id, [])
        tile = table_state(
            TableFacts(
                table_id=str(t.id),
                label=t.label,
                kind=t.kind,
                cleared_at=t.cleared_at,
                last_session_at=last_session.get(t.id),
                open_bill=bill is not None,
                paying_since=bill.bill_requested_at if bill else None,
                oldest_placed_at=bill.oldest if bill else None,
                has_active_orders=bool(bill and bill.active),
                last_settled_at=last_settled.get(t.id),
                last_cancelled_at=last_cancelled.get(t.id),
                call_reason=call.reason if call else None,
                call_since=call.created_at if call else None,
                running_total=total,
                sitting_open=sitting is not None,
                sitting_opened_at=sitting.opened_at if sitting else None,
                approval_pending=pend[0].placed_at if pend else None,
            ),
            now,
        )
        if tile is None:
            continue
        tiles.append(
            FloorTile(
                table_id=t.id,
                label=t.label,
                state=tile.state,
                level=tile.level,
                since=tile.since,
                reason=tile.reason,
                reason_label=reason_label(tile.reason, extra),
                running_total=total,
                bill_id=bill.id if bill else None,
                call_id=call.id if call else None,
                sitting_open=sitting is not None,
                waiting_for_open=tile.waiting_for_open,
                pending_order_id=pend[0].id if pend else None,
                pending_order_ids=[o.id for o in pend],
                pending_order_total=sum((o.total for o in pend), Decimal("0")) if pend else None,
                pending_order_items=sum(i.quantity for o in pend for i in o.items)
                if pend
                else None,
            )
        )
    tiles.sort(key=lambda x: (LEVEL_ORDER[x.level], _natural(x.label)))
    return FloorResponse(
        tiles=tiles,
        counts={lvl: sum(x.level == lvl for x in tiles) for lvl in ("red", "amber")},
        thresholds={
            s: [int(a.total_seconds()), int(r.total_seconds())] for s, (a, r) in THRESHOLDS.items()
        },
        server_time=now,
        service_extra_label=extra,
        pay_forward_balance=await pay_forward.balance(db, rid),
    )


@router.post(
    "/pay-forward/give",
    response_model=GiveResponse,
    responses={**RESPONSES, 409: {"description": "None waiting"}},
)
async def give_pay_forward(
    payload: GiveRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> GiveResponse:
    """Hand out one pay-it-forward chai: a free kitchen ticket, never revenue."""
    rid = access.restaurant.id
    handout_id, replayed = await pay_forward.give(
        db, access.restaurant, access.user.id, payload.idempotency_key
    )
    left = await pay_forward.balance(db, rid)
    await db.commit()
    if replayed:  # the first call already told the kitchen
        return GiveResponse(order_id=handout_id, pay_forward_balance=left)
    order_id = str(handout_id)
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "pay_forward_given", "order_id": order_id})
    )
    placed = json.dumps({"event": "order_placed", "order_id": order_id})
    await publish_event(f"kitchen:{rid}", placed)
    await publish_event(f"orders:{order_id}", placed)
    return GiveResponse(order_id=handout_id, pay_forward_balance=left)


@router.post(
    "/tables/{table_id}/clear",
    response_model=TableClearedResponse,
    responses={
        **RESPONSES,
        409: {"description": "Settle the bill first, or new guests are already seated"},
    },
)
async def clear_table(
    table_id: uuid.UUID,
    payload: ClearTableRequest | None = None,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> TableClearedResponse:
    rid = access.restaurant.id
    table = (
        await db.execute(
            select(DiningTable)
            .where(DiningTable.id == table_id, DiningTable.restaurant_id == rid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    open_bill = await db.scalar(
        select(Bill.id).where(Bill.table_id == table.id, Bill.status == "open").limit(1)
    )
    if open_bill is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Settle the bill first")
    now = await db.scalar(select(func.clock_timestamp()))
    force = bool(payload and payload.force)
    if not force:
        # A live phone scanned after the last reset: clearing would end the new party's visit.
        seated = select(GuestSession.id).where(
            GuestSession.table_id == table.id, GuestSession.expires_at > now
        )
        if table.reset_at is not None:  # same reset as session_is_current
            seated = seated.where(GuestSession.created_at > table.reset_at)
        if await db.scalar(seated.limit(1)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="New guests are already seated"
            )
    table.cleared_at = now
    await mark_table_reset(db, table.id)
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_cleared",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id), "force": force},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_cleared", "table_id": str(table.id)})
    )
    return TableClearedResponse(table_id=table.id, cleared_at=table.cleared_at)


async def _table(db: AsyncSession, rid: uuid.UUID, table_id: uuid.UUID) -> DiningTable:
    table = (
        await db.execute(
            select(DiningTable).where(DiningTable.id == table_id, DiningTable.restaurant_id == rid)
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.post(
    "/tables/{table_id}/sitting",
    response_model=OpenSittingResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **RESPONSES,
        409: {"description": "Table is already open, is a counter, or has an unpaid bill"},
    },
)
async def open_table(
    table_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> OpenSittingResponse:
    """Staff seat a party: guests at this table may order once it is open."""
    rid = access.restaurant.id
    table = await _table(db, rid, table_id)
    if table.kind != "table":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Counter tables are not opened"
        )
    # A party seated now would join the previous party's unpaid bill.
    open_bill = await db.scalar(
        select(Bill.id).where(Bill.table_id == table.id, Bill.status == "open").limit(1)
    )
    if open_bill is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Settle the bill first")
    cancelled: list[uuid.UUID] = []  # by an idle close of the previous party's sitting
    if await get_open_sitting(db, table.id, cancelled) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Table is already open")
    try:
        sitting = await open_sitting_for_table(
            db, table.id, access.user.id, access.restaurant.sitting_code_required
        )
    except IntegrityError:  # a concurrent open won the one-open-sitting-per-table index
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Table is already open"
        ) from None
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_opened",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id), "sitting_id": str(sitting.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_opened", "table_id": str(table.id)})
    )
    await publish_declined(rid, cancelled)
    return OpenSittingResponse(
        sitting_id=sitting.id, code=sitting.code, opened_at=sitting.opened_at
    )


@router.delete(
    "/tables/{table_id}/sitting",
    response_model=CloseSittingResponse,
    responses={**RESPONSES, 409: {"description": "Settle the bill first, or no sitting is open"}},
)
async def close_table(
    table_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> CloseSittingResponse:
    rid = access.restaurant.id
    table = await _table(db, rid, table_id)
    # Bill lock before the sitting lock, as create/approve take them: an approval racing this
    # close has either opened its bill (refused here) or waits until the sitting is closed.
    if await lock_open_bill(db, rid, table.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Settle the bill first")
    cancelled: list[uuid.UUID] = []
    if await get_open_sitting(db, table.id, cancelled) is None:
        await db.commit()  # keep an idle close get_open_sitting may have just made
        await publish_declined(rid, cancelled)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No sitting is open")
    now = await db.scalar(select(func.clock_timestamp()))
    # Waiting orders (no bill) are allowed: closing the table cancels them.
    cancelled = await close_sitting_for_table(db, table.id, "staff_closed", now, access.user.id)
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_closed",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_closed", "table_id": str(table.id)})
    )
    await publish_declined(rid, cancelled)
    return CloseSittingResponse(table_id=table.id, closed_at=now)


APPROVAL_409 = {409: {"description": "The waiting orders changed, or already handled"}}


@router.post(
    "/tables/{table_id}/approve",
    response_model=ApprovalResponse,
    responses={**RESPONSES, **APPROVAL_409},
)
async def approve_table(
    table_id: uuid.UUID,
    payload: ApprovalRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    """Send the waiting orders the waiter saw to the kitchen; a repeated tap replays."""
    rid = access.restaurant.id
    table = await _table(db, rid, table_id)
    bill, created = await approve_pending(
        db, rid, table.id, f"user:{access.user.id}", payload.order_ids
    )
    await db.commit()
    if bill is not None:  # else a replay: the first tap already told everyone
        for order_id in payload.order_ids:
            placed = json.dumps({"event": "order_placed", "order_id": str(order_id)})
            await publish_event(f"kitchen:{rid}", placed)
            await publish_event(f"orders:{order_id}", placed)
        if created:
            await publish_event(
                f"kitchen:{rid}", json.dumps({"event": "bill_opened", "bill_id": str(bill.id)})
            )
    return ApprovalResponse(table_id=table.id, order_ids=payload.order_ids, status="placed")


@router.post(
    "/tables/{table_id}/decline",
    response_model=ApprovalResponse,
    responses={**RESPONSES, **APPROVAL_409},
)
async def decline_table(
    table_id: uuid.UUID,
    payload: ApprovalRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    """Cancel the waiting orders the waiter saw ("Not now"); the table stays open."""
    rid = access.restaurant.id
    table = await _table(db, rid, table_id)
    declined = await decline_pending(db, rid, table.id, access.user.id, payload.order_ids)
    await db.commit()
    if declined:
        await publish_declined(rid, payload.order_ids)
    return ApprovalResponse(table_id=table.id, order_ids=payload.order_ids, status="cancelled")


@router.post(
    "/service-calls/{call_id}/resolve",
    response_model=ServiceCallResponse,
    responses={**RESPONSES, 409: {"description": "Call already resolved"}},
)
async def resolve_call(
    call_id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> ServiceCallResponse:
    rid = access.restaurant.id
    call = (
        await db.execute(
            select(ServiceCall)
            .where(ServiceCall.id == call_id, ServiceCall.restaurant_id == rid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.resolved_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Call already resolved")
    call.resolved_at = await db.scalar(select(func.clock_timestamp()))
    call.resolved_by = access.user.id
    payload = {"call_id": str(call.id), "table_id": str(call.table_id)}
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="service_call_resolved",
            actor=f"user:{access.user.id}",
            payload=payload,
        )
    )
    await db.commit()
    await publish_event(f"kitchen:{rid}", json.dumps({"event": "service_call_resolved", **payload}))
    return call_response(call, access.restaurant.service_extra_label)
