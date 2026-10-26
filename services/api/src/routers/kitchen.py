"""Kitchen display, order bumping, recall, and SSE stream endpoints."""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, member_access
from src.database import get_db
from src.models.audit import AuditLog
from src.models.dining_table import DiningTable
from src.models.order import Order
from src.redis_client import publish_event, redis_client
from src.schemas.kitchen import (
    KitchenOrderItemResponse,
    KitchenOrderResponse,
    KitchenOrdersListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/restaurants/{slug}/kitchen", tags=["kitchen"])


def _build_kitchen_order_response(
    order: Order,
    table_labels: dict[uuid.UUID, str],
) -> KitchenOrderResponse:
    items_resp: list[KitchenOrderItemResponse] = []
    for item in order.items:
        matched = [a for a in item.allergens if a in order.allergens_to_avoid]
        has_conflict = len(matched) > 0
        items_resp.append(
            KitchenOrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                kitchen_name=item.kitchen_name,
                option_label=item.option_label,
                quantity=item.quantity,
                notes=item.notes,
                allergens=item.allergens,
                allergen_status=item.allergen_status,
                allergen_verified=item.allergen_verified,
                conflict_with_order_allergens=has_conflict,
                matched_allergens=matched,
            )
        )

    return KitchenOrderResponse(
        id=order.id,
        restaurant_id=order.restaurant_id,
        table_id=order.table_id,
        table_label=table_labels.get(order.table_id) if order.table_id else None,
        status=order.status,
        allergens_to_avoid=order.allergens_to_avoid,
        dietary_preferences=order.dietary_preferences,
        allergen_conflict_acknowledged=order.allergen_conflict_acknowledged,
        placed_at=order.placed_at,
        bumped_at=order.bumped_at,
        items=items_resp,
    )


@router.get(
    "/orders",
    response_model=KitchenOrdersListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized"},
        404: {"description": "Restaurant not found"},
    },
)
async def get_kitchen_orders(
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> KitchenOrdersListResponse:
    """Return placed orders plus the most recent order bumped within the last 60 seconds."""
    restaurant = access.restaurant

    # 1. Fetch tables for label resolution
    stmt_tables = select(DiningTable).where(DiningTable.restaurant_id == restaurant.id)
    res_tables = await db.execute(stmt_tables)
    table_labels = {t.id: t.label for t in res_tables.scalars().all()}

    # 2. Query placed orders
    stmt_placed = (
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.restaurant_id == restaurant.id,
            Order.status == "placed",
        )
        .order_by(Order.placed_at.asc())
    )
    res_placed = await db.execute(stmt_placed)
    placed_orders = list(res_placed.scalars().all())

    # 3. Query most recent bumped order within the last 60 seconds
    cutoff = datetime.now(UTC) - timedelta(seconds=60)
    stmt_bumped = (
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.restaurant_id == restaurant.id,
            Order.status == "bumped",
            Order.bumped_at >= cutoff,
        )
        .order_by(Order.bumped_at.desc())
        .limit(1)
    )
    res_bumped = await db.execute(stmt_bumped)
    recent_bumped = list(res_bumped.scalars().all())

    combined_orders = placed_orders + recent_bumped
    result = [_build_kitchen_order_response(o, table_labels) for o in combined_orders]
    return KitchenOrdersListResponse(orders=result)


@router.get(
    "/stream",
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized"},
        404: {"description": "Restaurant not found"},
    },
)
async def stream_kitchen_orders(
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream kitchen change notifications via Server-Sent Events.

    Generators hold no database session.
    """
    restaurant = access.restaurant
    await db.close()

    channel_name = f"kitchen:{restaurant.id}"

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        last_heartbeat = time.time()
        try:
            yield 'data: {"event": "connected"}\n\n'
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("data"):
                    yield f"data: {msg['data']}\n\n"
                    last_heartbeat = time.time()
                elif time.time() - last_heartbeat >= 15.0:
                    yield 'data: {"event": "heartbeat"}\n\n'
                    last_heartbeat = time.time()
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/orders/{id}/bump",
    response_model=KitchenOrderResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized"},
        404: {"description": "Order not found"},
        409: {"description": "Order was cancelled"},
    },
)
async def bump_order(
    id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> KitchenOrderResponse:
    """Mark an order as bumped. Idempotent: already bumped order returns existing bumped_at."""
    restaurant = access.restaurant

    # Locked: a concurrent void commits first or waits, and the status checks below see it.
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == id, Order.restaurant_id == restaurant.id)
        .with_for_update(of=Order)
        .execution_options(populate_existing=True)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Fetch table labels
    stmt_tables = select(DiningTable).where(DiningTable.restaurant_id == restaurant.id)
    res_tables = await db.execute(stmt_tables)
    table_labels = {t.id: t.label for t in res_tables.scalars().all()}

    if order.status == "bumped":
        # Already bumped: idempotent return
        return _build_kitchen_order_response(order, table_labels)
    if order.status != "placed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order was cancelled")

    now = datetime.now(UTC)
    order.status = "bumped"
    order.bumped_at = now

    audit = AuditLog(
        restaurant_id=restaurant.id,
        event_type="order_bumped",
        actor=f"user:{access.user.id}",
        payload={"order_id": str(order.id), "bumped_at": str(now)},
    )
    db.add(audit)
    await db.commit()
    res_order = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = res_order.scalar_one()

    # Publish events
    event_payload = json.dumps({"event": "order_bumped", "order_id": str(order.id)})
    await publish_event(f"kitchen:{restaurant.id}", event_payload)
    await publish_event(f"orders:{order.id}", event_payload)

    return _build_kitchen_order_response(order, table_labels)


@router.post(
    "/orders/{id}/recall",
    response_model=KitchenOrderResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized"},
        404: {"description": "Order not found"},
        409: {"description": "Recall window expired or order not bumped"},
    },
)
async def recall_order(
    id: uuid.UUID,
    access: RestaurantAccess = Depends(member_access),
    db: AsyncSession = Depends(get_db),
) -> KitchenOrderResponse:
    """Recall an order if within 60s of bump. Sets status back to placed."""
    restaurant = access.restaurant

    # Locked: a concurrent void commits first or waits, and the status checks below see it.
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == id, Order.restaurant_id == restaurant.id)
        .with_for_update(of=Order)
        .execution_options(populate_existing=True)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status != "bumped" or order.bumped_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is not in bumped status",
        )

    now = datetime.now(UTC)
    elapsed_seconds = (now - order.bumped_at).total_seconds()
    if elapsed_seconds >= 60.0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order recall window expired (exceeded 60 seconds)",
        )

    previous_bumped_at = order.bumped_at
    order.status = "placed"
    order.bumped_at = None

    audit = AuditLog(
        restaurant_id=restaurant.id,
        event_type="order_recalled",
        actor=f"user:{access.user.id}",
        payload={"order_id": str(order.id), "previous_bumped_at": str(previous_bumped_at)},
    )
    db.add(audit)
    await db.commit()
    res_order = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = res_order.scalar_one()

    # Fetch table labels
    stmt_tables = select(DiningTable).where(DiningTable.restaurant_id == restaurant.id)
    res_tables = await db.execute(stmt_tables)
    table_labels = {t.id: t.label for t in res_tables.scalars().all()}

    event_payload = json.dumps({"event": "order_recalled", "order_id": str(order.id)})
    await publish_event(f"kitchen:{restaurant.id}", event_payload)
    await publish_event(f"orders:{order.id}", event_payload)

    return _build_kitchen_order_response(order, table_labels)
