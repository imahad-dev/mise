"""Table bills for staff and owners: list, detail with tax previews, settle."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.access import RestaurantAccess, member_access
from src.database import get_db
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.models.restaurant import Restaurant
from src.redis_client import publish_event
from src.schemas.bills import BillDetail, BillListResponse, BillSummary, SettleBillRequest
from src.services.bills import CENTS, active_orders, bill_lines, local_date, previews, settle_bill

router = APIRouter(prefix="/api/restaurants/{slug}/bills", tags=["bills"])

RESPONSES = {
    401: {"description": "Unauthenticated"},
    404: {"description": "Restaurant or bill not found"},
}


async def bill_detail(db: AsyncSession, restaurant: Restaurant, bill: Bill) -> BillDetail:
    orders = await active_orders(db, bill.id)
    lines, subtotal = bill_lines(orders)
    label = (
        await db.scalar(select(DiningTable.label).where(DiningTable.id == bill.table_id))
        if bill.table_id
        else None
    )
    standard, digital = previews(
        restaurant.tax_jurisdiction,
        subtotal,
        local_date(restaurant, bill.settled_at or datetime.now(UTC)),
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
        currency=restaurant.currency,
    )


@router.get("", response_model=BillListResponse, responses=RESPONSES)
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
        bills=[
            BillSummary(
                id=bill.id,
                bill_no=bill.bill_no,
                table_label=label,
                status=bill.status,
                opened_at=bill.opened_at,
                order_count=count,
                subtotal=(subtotal or Decimal("0")).quantize(CENTS),
                bill_requested_at=bill.bill_requested_at,
            )
            for bill, label, count, subtotal in rows
        ]
    )


@router.get("/{bill_id}", response_model=BillDetail, responses=RESPONSES)
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
    "/{bill_id}/settle",
    response_model=BillDetail,
    responses={
        **RESPONSES,
        409: {"description": "Bill already settled"},
        422: {"description": "No active orders or no tax rate configured"},
    },
)
async def settle(
    bill_id: uuid.UUID,
    payload: SettleBillRequest,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> BillDetail:
    bill = await settle_bill(
        db, bill_id, access.restaurant, payload.payment_method, payload.payment_reference
    )
    await db.commit()
    await publish_event(
        f"kitchen:{access.restaurant.id}",
        json.dumps({"event": "bill_settled", "bill_id": str(bill.id)}),
    )
    return await bill_detail(db, access.restaurant, bill)
