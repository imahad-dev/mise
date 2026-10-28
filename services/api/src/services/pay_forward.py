"""Pay-it-forward chai: guests buy one for someone else, staff hand them out for free."""

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.audit import AuditLog
from src.models.menu import MenuItem
from src.models.order import Order
from src.models.pay_forward import PayForward
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.order_snapshot import snapshot_order_item

NONE_WAITING = "None waiting"


async def balance(db: AsyncSession, restaurant_id: uuid.UUID) -> int:
    """Chai bought and not yet handed out."""
    signed = case((PayForward.kind == "bought", PayForward.quantity), else_=-PayForward.quantity)
    total = await db.scalar(
        select(func.coalesce(func.sum(signed), 0)).where(PayForward.restaurant_id == restaurant_id)
    )
    return int(total)


async def record_bought(db: AsyncSession, restaurant_id: uuid.UUID, orders: list[Order]) -> None:
    """One 'bought' row per pay-it-forward line of the given (settled, unvoided) orders."""
    item_ids = {oi.menu_item_id for o in orders for oi in o.items}
    if not item_ids:
        return
    flagged = set(
        (
            await db.scalars(
                select(MenuItem.id).where(MenuItem.id.in_(item_ids), MenuItem.is_pay_forward)
            )
        ).all()
    )
    for o in orders:
        for oi in o.items:
            if oi.menu_item_id in flagged:
                db.add(
                    PayForward(
                        restaurant_id=restaurant_id,
                        kind="bought",
                        quantity=oi.quantity,
                        order_id=o.id,
                    )
                )


async def give(db: AsyncSession, restaurant: Restaurant, user_id: uuid.UUID) -> Order:
    """Hand out one chai: a free kitchen ticket with no bill. Caller commits and publishes."""
    # Serialises gives per venue, so the balance read below cannot go stale before the insert.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"payforward:{restaurant.id}")))
    )
    if await balance(db, restaurant.id) < 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NONE_WAITING)
    item = (
        await db.execute(
            select(MenuItem)
            .options(selectinload(MenuItem.translations))
            .where(
                MenuItem.restaurant_id == restaurant.id,
                MenuItem.is_pay_forward,
                MenuItem.deleted_at.is_(None),
            )
            .order_by(MenuItem.sort_order, MenuItem.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NONE_WAITING)
    now = await db.scalar(select(func.clock_timestamp()))
    # Already expired, like the simulator's: a handout has no guest and no personal data.
    session = GuestSession(
        restaurant_id=restaurant.id, language=restaurant.default_language, expires_at=now
    )
    db.add(session)
    await db.flush()
    line = snapshot_order_item(
        item,
        quantity=1,
        notes=None,
        guest_language=restaurant.default_language,
        default_language=restaurant.default_language,
        guest_allergens_to_avoid=[],
    )
    line.unit_price = Decimal("0.00")  # free to the receiver; unit_cost stays the real cost
    order = Order(
        guest_session_id=session.id,
        restaurant_id=restaurant.id,
        status="placed",
        source="pay_forward",
        total=Decimal("0.00"),
        idempotency_key=f"pay_forward:{uuid.uuid4().hex}",
        payload_hash="pay_forward",
        items=[line],
    )
    db.add(order)
    await db.flush()
    db.add(
        PayForward(
            restaurant_id=restaurant.id,
            kind="given",
            quantity=1,
            order_id=order.id,
            user_id=user_id,
        )
    )
    db.add(
        AuditLog(
            restaurant_id=restaurant.id,
            event_type="pay_forward_given",
            actor=f"user:{user_id}",
            payload={"order_id": str(order.id), "quantity": 1},
        )
    )
    await db.flush()
    return order


async def window_totals(
    db: AsyncSession, restaurant_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, int]:
    """{'bought': n, 'given': m} recorded in [start, end)."""
    rows = await db.execute(
        select(PayForward.kind, func.sum(PayForward.quantity))
        .where(
            PayForward.restaurant_id == restaurant_id,
            PayForward.created_at >= start,
            PayForward.created_at < end,
        )
        .group_by(PayForward.kind)
    )
    out = {"bought": 0, "given": 0}
    out.update({k: int(n) for k, n in rows.all()})
    return out
