"""Orders router for guest order placement and streaming."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_guest_session
from src.database import get_db
from src.models.audit import AuditLog
from src.models.menu import MenuItem
from src.models.order import Order, OrderItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.redis_client import publish_event, redis_client
from src.schemas.orders import CreateOrderRequest, OrderItemRequest, OrderResponse
from src.services.allergen_service import compute_allergen_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def compute_payload_hash(items: list[OrderItemRequest]) -> str:
    """Compute deterministic SHA-256 hash of items and notes."""
    canonical = [
        {
            "menu_item_id": str(i.menu_item_id),
            "quantity": i.quantity,
            "notes": i.notes or "",
        }
        for i in sorted(
            items,
            key=lambda x: (str(x.menu_item_id), x.quantity, x.notes or ""),
        )
    ]
    raw = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Order already placed (idempotent replay)"},
        400: {"description": "Invalid order items"},
        409: {"description": "Idempotency conflict, unavailable items, or allergen ack required"},
    },
)
async def create_order(
    payload: CreateOrderRequest,
    response: Response,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> Order:
    """Place an order with canonical hash idempotency, allergen check, and audit logging."""
    payload_hash = compute_payload_hash(payload.items)

    # 1. Check for existing order with same (session, idempotency_key)
    stmt_existing = (
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.guest_session_id == session.id,
            Order.idempotency_key == payload.idempotency_key,
        )
    )
    res_existing = await db.execute(stmt_existing)
    existing_order = res_existing.scalar_one_or_none()

    if existing_order is not None:
        if existing_order.payload_hash == payload_hash:
            response.status_code = status.HTTP_200_OK
            return existing_order
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key mismatch with different payload",
        )

    # 2. Fetch menu items for this restaurant
    item_ids = [item_req.menu_item_id for item_req in payload.items]
    stmt_items = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(
            MenuItem.id.in_(item_ids),
            MenuItem.restaurant_id == session.restaurant_id,
            MenuItem.deleted_at.is_(None),
        )
    )
    res_items = await db.execute(stmt_items)
    found_items = {item.id: item for item in res_items.scalars().all()}

    missing = [
        str(req.menu_item_id) for req in payload.items if req.menu_item_id not in found_items
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Menu items not found: {missing}",
        )

    # 3. Check item availability
    unavailable_items = [
        {"menu_item_id": str(item.id), "category": item.category}
        for item in found_items.values()
        if not item.available
    ]
    if unavailable_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "unavailable_items", "unavailable_items": unavailable_items},
        )

    # 4. Fetch restaurant for default language
    stmt_rest = select(Restaurant).where(Restaurant.id == session.restaurant_id)
    res_rest = await db.execute(stmt_rest)
    restaurant = res_rest.scalar_one()

    # 5. Check allergen conflict against session's allergens_to_avoid
    conflict_items: list[dict] = []
    for req in payload.items:
        item = found_items[req.menu_item_id]
        s_val, matched = compute_allergen_status(
            item_allergens=item.allergens,
            allergen_verified=item.allergen_verified,
            allergens_to_avoid=session.allergens_to_avoid,
        )
        if s_val in ("contains", "unverified"):
            conflict_items.append(
                {
                    "menu_item_id": str(item.id),
                    "status": s_val,
                    "matched_allergens": matched,
                }
            )

    if conflict_items and not payload.acknowledge_allergen_risk:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "allergen_ack_required", "items": conflict_items},
        )

    # 6. Build snapshot OrderItems and calculate total
    total = Decimal("0.00")
    order_items: list[OrderItem] = []
    for req in payload.items:
        item = found_items[req.menu_item_id]
        line_total = item.price * Decimal(req.quantity)
        total += line_total

        trans_map = {t.language: t for t in item.translations}
        guest_trans = trans_map.get(session.language) or trans_map.get(restaurant.default_language)
        default_trans = trans_map.get(restaurant.default_language) or next(
            iter(trans_map.values()), None
        )

        item_name = guest_trans.name if guest_trans else ""
        kitchen_name = default_trans.name if default_trans else ""

        s_val, _ = compute_allergen_status(
            item.allergens,
            item.allergen_verified,
            session.allergens_to_avoid,
        )

        order_items.append(
            OrderItem(
                menu_item_id=item.id,
                quantity=req.quantity,
                unit_price=item.price,
                unit_cost=item.unit_cost,
                item_name=item_name,
                kitchen_name=kitchen_name,
                allergens=list(item.allergens),
                allergen_verified=item.allergen_verified,
                allergen_status=s_val,
                notes=req.notes,
            )
        )

    order = Order(
        guest_session_id=session.id,
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        status="placed",
        total=total,
        idempotency_key=payload.idempotency_key,
        payload_hash=payload_hash,
        allergen_conflict_acknowledged=bool(payload.acknowledge_allergen_risk),
        allergens_to_avoid=list(session.allergens_to_avoid),
        dietary_preferences=list(session.dietary_preferences),
        items=order_items,
    )

    # 7. Commit with concurrent duplicate protection
    try:
        db.add(order)
        await db.flush()

        # Write audit log for conflict acknowledgment if applicable
        if conflict_items and payload.acknowledge_allergen_risk:
            audit_ack = AuditLog(
                restaurant_id=session.restaurant_id,
                event_type="allergen_conflict_acknowledged",
                actor=f"guest:{session.id}",
                payload={"items": conflict_items},
            )
            db.add(audit_ack)

        # Write audit log for order placed with populated order.id
        audit_placed = AuditLog(
            restaurant_id=session.restaurant_id,
            event_type="order_placed",
            actor=f"guest:{session.id}",
            payload={"order_id": str(order.id), "total": str(total), "lines": len(order_items)},
        )
        db.add(audit_placed)

        await db.commit()
    except IntegrityError as err:
        await db.rollback()
        # Query existing order created by concurrent thread
        res_conc = await db.execute(stmt_existing)
        conc_order = res_conc.scalar_one_or_none()
        if conc_order is not None and conc_order.payload_hash == payload_hash:
            response.status_code = status.HTTP_200_OK
            return conc_order
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order conflict",
        ) from err

    # Re-fetch order with items eager-loaded
    res_final = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    final_order = res_final.scalar_one()

    # 8. Publish Redis change signal AFTER commit (publish failures never fail the order)
    order_event = json.dumps({"event": "order_placed", "order_id": str(final_order.id)})
    await publish_event(f"kitchen:{final_order.restaurant_id}", order_event)
    await publish_event(f"orders:{final_order.id}", order_event)

    response.status_code = status.HTTP_201_CREATED
    return final_order


@router.get(
    "/{id}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Order not found"}},
)
async def get_order(
    id: uuid.UUID,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> Order:
    """Retrieve an order. Returns 404 unless order belongs to the session cookie's session."""
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == id, Order.guest_session_id == session.id)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


@router.get(
    "/{id}/stream",
    responses={404: {"description": "Order not found"}},
)
async def stream_order(
    id: uuid.UUID,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream order status updates via Server-Sent Events with 15s heartbeats.

    Generators hold no database session.
    """
    stmt = select(Order.id).where(Order.id == id, Order.guest_session_id == session.id)
    res = await db.execute(stmt)
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await db.close()

    channel_name = f"orders:{id}"

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
