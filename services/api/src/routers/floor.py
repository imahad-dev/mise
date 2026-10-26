"""Floor view for staff: table tiles with timing levels, clearing, resolving waiter calls."""

import json
import re
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.access import RestaurantAccess, member_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.service_call import ServiceCall
from src.models.session import GuestSession
from src.redis_client import publish_event
from src.schemas.floor import (
    FloorResponse,
    FloorTile,
    ServiceCallResponse,
    TableClearedResponse,
    call_response,
)
from src.services.bills import CENTS
from src.services.floor import THRESHOLDS, TableFacts, reason_label, table_state

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

    extra = access.restaurant.service_extra_label
    tiles: list[FloorTile] = []
    for t in tables:
        bill = open_bills.get(t.id)
        call = calls.get(t.id)
        total = (bill.total or Decimal("0")).quantize(CENTS) if bill else None
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
                call_reason=call.reason if call else None,
                call_since=call.created_at if call else None,
                running_total=total,
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
    )


@router.post(
    "/tables/{table_id}/clear",
    response_model=TableClearedResponse,
    responses={**RESPONSES, 409: {"description": "Settle the bill first"}},
)
async def clear_table(
    table_id: uuid.UUID,
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
    table.cleared_at = await db.scalar(select(func.clock_timestamp()))
    db.add(
        AuditLog(
            restaurant_id=rid,
            event_type="table_cleared",
            actor=f"user:{access.user.id}",
            payload={"table_id": str(table.id)},
        )
    )
    await db.commit()
    await publish_event(
        f"kitchen:{rid}", json.dumps({"event": "table_cleared", "table_id": str(table.id)})
    )
    return TableClearedResponse(table_id=table.id, cleared_at=table.cleared_at)


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
