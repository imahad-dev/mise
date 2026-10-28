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
from src.models.order import Order, OrderItem
from src.models.pay_forward import PayForward
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.services.order_snapshot import snapshot_order_item

NONE_WAITING = "None waiting"
ALREADY_FLAGGED = "Another item is already the pay-it-forward chai"


async def lock(db: AsyncSession, restaurant_id: uuid.UUID) -> None:
    """Serialises gives and changes to the venue's pay-it-forward item until the txn ends."""
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"payforward:{restaurant_id}")))
    )


async def balance(db: AsyncSession, restaurant_id: uuid.UUID) -> int:
    """Chai bought and not yet handed out."""
    signed = case((PayForward.kind == "bought", PayForward.quantity), else_=-PayForward.quantity)
    total = await db.scalar(
        select(func.coalesce(func.sum(signed), 0)).where(PayForward.restaurant_id == restaurant_id)
    )
    return int(total)


async def record_bought(db: AsyncSession, restaurant_id: uuid.UUID, orders: list[Order]) -> None:
    """One 'bought' row per pay-it-forward line of the given (settled, unvoided) orders.

    Reads the line's snapshot of the flag: re-flagging the menu item later changes nothing.
    """
    for o in orders:
        for oi in o.items:
            if oi.is_pay_forward:
                db.add(
                    PayForward(
                        restaurant_id=restaurant_id,
                        kind="bought",
                        quantity=oi.quantity,
                        order_id=o.id,
                    )
                )


async def ensure_can_remove(db: AsyncSession, restaurant_id: uuid.UUID) -> None:
    """Refuse to unflag or delete the pay-it-forward item while chai are still waiting."""
    await lock(db, restaurant_id)
    waiting = await balance(db, restaurant_id)
    if waiting > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{waiting} chai are still waiting to be given; "
                "give them out before removing this item"
            ),
        )


async def ensure_can_flag(db: AsyncSession, restaurant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """At most one live pay-it-forward item per venue (also a partial unique index)."""
    await lock(db, restaurant_id)
    other = await db.scalar(
        select(MenuItem.id).where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.is_pay_forward,
            MenuItem.deleted_at.is_(None),
            MenuItem.id != item_id,
        )
    )
    if other is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_FLAGGED)


async def _handout_item(db: AsyncSession, restaurant_id: uuid.UUID) -> MenuItem | None:
    """The live flagged item; else the item of the latest pay-it-forward line sold, so a credit
    bought while the item was flagged can always be handed out."""
    query = select(MenuItem).options(selectinload(MenuItem.translations))
    item = (
        await db.execute(
            query.where(
                MenuItem.restaurant_id == restaurant_id,
                MenuItem.is_pay_forward,
                MenuItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if item is not None:
        return item
    last_sold = (
        select(OrderItem.menu_item_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.restaurant_id == restaurant_id, OrderItem.is_pay_forward)
        .order_by(OrderItem.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    return (await db.execute(query.where(MenuItem.id == last_sold))).scalar_one_or_none()


async def give(
    db: AsyncSession, restaurant: Restaurant, user_id: uuid.UUID, idempotency_key: str
) -> tuple[uuid.UUID, bool]:
    """Hand out one chai: a free kitchen ticket with no bill. Caller commits and publishes.

    Returns (handout order id, replayed). A key already used returns its first handout and
    writes nothing: the lock makes a concurrent same-key call wait and then see that row.
    """
    await lock(db, restaurant.id)
    previous = (
        await db.execute(
            select(PayForward.order_id).where(
                PayForward.restaurant_id == restaurant.id,
                PayForward.idempotency_key == idempotency_key,
            )
        )
    ).one_or_none()
    if previous is not None:
        if previous.order_id is None:  # its handout order was deleted since
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already given")
        return previous.order_id, True
    if await balance(db, restaurant.id) < 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NONE_WAITING)
    item = await _handout_item(db, restaurant.id)
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
    line.is_pay_forward = False  # a handout is never bought again
    order = Order(
        guest_session_id=session.id,
        restaurant_id=restaurant.id,
        status="placed",
        source="pay_forward",
        total=Decimal("0.00"),
        idempotency_key=f"pay_forward:{idempotency_key}",
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
            idempotency_key=idempotency_key,
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
    return order.id, False


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
