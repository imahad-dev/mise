"""Orders router for guest order placement and streaming."""

import asyncio
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_guest_session
from src.database import get_db
from src.models.audit import AuditLog
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption
from src.models.order import Order, OrderItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.redis_client import publish_event, redis_client
from src.request_limits import enforce_session_limit
from src.schemas.orders import CreateOrderRequest, OrderItemRequest, OrderResponse
from src.services.allergen_service import compute_allergen_status
from src.services.bills import (
    VISIT_ENDED,
    lock_open_bill,
    open_bill_for_table,
    session_is_current,
)
from src.services.counter import open_counter_bill
from src.services.order_snapshot import line_total, snapshot_order_item
from src.services.sitting import get_open_sitting, has_approved_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def compute_payload_hash(items: list[OrderItemRequest]) -> str:
    """Compute deterministic SHA-256 hash of items and notes."""
    canonical = [
        {
            "menu_item_id": str(i.menu_item_id),
            "option_id": str(i.option_id or ""),
            "quantity": i.quantity,
            "notes": i.notes or "",
        }
        for i in sorted(
            items,
            key=lambda x: (str(x.menu_item_id), str(x.option_id or ""), x.quantity, x.notes or ""),
        )
    ]
    raw = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_idempotency_unique_violation(err: IntegrityError) -> bool:
    """Check if IntegrityError is specifically SQLSTATE 23505 on the idempotency constraint."""
    orig = getattr(err, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    err_str = str(err).lower()

    is_23505 = (sqlstate == "23505") or ("23505" in err_str)
    if not is_23505:
        return False

    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name is None and hasattr(orig, "diag"):
        constraint_name = getattr(orig.diag, "constraint_name", None)

    if constraint_name:
        return constraint_name == "orders_guest_idempotency_key"

    return "orders_guest_idempotency_key" in err_str or "idempotency_key" in err_str


async def order_response(
    db: AsyncSession, order: Order, over_first_order_cap: bool = False
) -> OrderResponse:
    """OrderResponse with the venue currency, loaded explicitly (relationships are lazy="raise")."""
    currency = await db.scalar(
        select(Restaurant.currency).where(Restaurant.id == order.restaurant_id)
    )
    computed = {"currency": currency, "over_first_order_cap": over_first_order_cap}
    fields = {
        name: getattr(order, name) for name in OrderResponse.model_fields if name not in computed
    }
    return OrderResponse.model_validate({**fields, **computed}, from_attributes=True)


CODE_TRIES = 5  # wrong table codes in a row before the phone waits CODE_LOCK_S
CODE_LOCK_S = 60
TOO_MANY_TRIES = "Too many tries. Please wait a minute and ask your waiter."
ORDERING_QUICKLY = "You're ordering quickly! Please wait a moment and try again."


async def _check_table_code(session: GuestSession, sitting: TableSitting, code: str | None) -> None:
    """403 unless `code` is the visit's table code; 429 while the phone is locked out.

    Redis errors skip the lockout (fail open, like the other limits); the code comparison
    itself never does.
    """
    lock_key, tries_key = f"code_lock:{session.id}", f"code_attempts:{session.id}"
    try:
        locked = await redis_client.exists(lock_key)
    except Exception as e:
        logger.warning("Redis error reading %s: %s", lock_key, e)
        locked = False
    if locked:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=TOO_MANY_TRIES)
    if code is not None and sitting.code is not None and secrets.compare_digest(code, sitting.code):
        try:
            await redis_client.delete(tries_key)
        except Exception as e:
            logger.warning("Redis error clearing %s: %s", tries_key, e)
        return
    if code is not None:  # a missing code is a prompt, not a wrong try
        try:
            tries = await redis_client.incr(tries_key)
            if tries == 1:
                await redis_client.expire(tries_key, 300)
            if tries >= CODE_TRIES:
                await redis_client.set(lock_key, "1", ex=CODE_LOCK_S)
                await redis_client.delete(tries_key)
        except Exception as e:
            logger.warning("Redis error counting %s: %s", tries_key, e)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "code_required"})


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": OrderResponse,
            "description": "Order already placed (idempotent replay)",
        },
        400: {"description": "Invalid order items"},
        403: {"description": "The table code is required or wrong"},
        409: {
            "description": "Table not open, idempotency conflict, unavailable items, "
            "or allergen ack required"
        },
        429: {"description": "Too many orders or wrong table codes from this phone"},
    },
)
async def create_order(
    payload: CreateOrderRequest,
    response: Response,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
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
            return await order_response(db, existing_order)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key mismatch with different payload",
        )

    # 1b. A table order needs an open table (and its code); counters and replays don't.
    at_counter = session.table_id is not None and (
        await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
        == "counter"
    )
    sitting: TableSitting | None = None
    bill = None
    if session.table_id is not None and not at_counter:
        # Bill lock before the sitting lock, the order every path takes.
        bill = await lock_open_bill(db, session.restaurant_id, session.table_id)
        sitting = await get_open_sitting(db, session.table_id)
        # A phone from an earlier sitting rescans the QR to join the new party's visit.
        if sitting is None or session.sitting_id not in (None, sitting.id):
            await db.commit()  # keep an idle close get_open_sitting may have just made
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"error": "table_not_open"}
            )
        # After the bill lock (a racing settle is committed by now), before any code try.
        if not await session_is_current(db, session):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=VISIT_ENDED)
        if sitting.code_required and session.sitting_id != sitting.id:
            await _check_table_code(session, sitting, payload.code)
        session.sitting_id = sitting.id

    # 2. Fetch menu items for this restaurant
    item_ids = [item_req.menu_item_id for item_req in payload.items]
    stmt_items = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations), selectinload(MenuItem.options))
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

    # 4b. Resolve each line's option (422 before any allergen check)
    line_options: list[MenuItemOption | None] = []
    for req in payload.items:
        item = found_items[req.menu_item_id]
        opts = {o.id: o for o in item.options}
        if opts and req.option_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Choose a size for {item.id}",
            )
        if req.option_id is not None and req.option_id not in opts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown option for {item.id}",
            )
        line_options.append(opts.get(req.option_id))

    # 5. Check allergen conflict against session's allergens_to_avoid
    conflict_items: list[dict] = []
    for req in payload.items:
        item = found_items[req.menu_item_id]
        s_val = compute_allergen_status(
            item_allergens=item.allergens,
            allergen_verified=item.allergen_verified,
            guest_allergens_to_avoid=session.allergens_to_avoid,
        )
        matched = (
            [a for a in item.allergens if a in session.allergens_to_avoid]
            if s_val == "contains"
            else []
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
    order_items: list[OrderItem] = [
        snapshot_order_item(
            found_items[req.menu_item_id],
            quantity=req.quantity,
            notes=req.notes,
            guest_language=session.language,
            default_language=restaurant.default_language,
            guest_allergens_to_avoid=session.allergens_to_avoid,
            option=opt,
        )
        for req, opt in zip(payload.items, line_options, strict=True)
    ]
    total = sum((line_total(oi) for oi in order_items), Decimal("0.00"))

    has_conflict = bool(conflict_items)
    ack_recorded = has_conflict and bool(payload.acknowledge_allergen_risk)

    # A visit's orders wait for the waiter until one of them is approved; a waiting order is
    # on no bill, so it never reaches any total.
    pending = sitting is not None and not await has_approved_order(db, sitting.id)
    bill_created = False
    if at_counter:
        # Every counter order is its own bill and pickup number, held until paid.
        bill, bill_created = await open_counter_bill(db, restaurant), True
    elif pending:
        bill = None
    elif sitting is not None:
        bill, bill_created = await open_bill_for_table(db, session.restaurant_id, session.table_id)

    over_first_order_cap = False
    if pending:
        # Base price of each dish on offer now; a dish's size options are not averaged in.
        avg_price = await db.scalar(
            select(func.avg(MenuItem.price)).where(
                MenuItem.restaurant_id == session.restaurant_id,
                MenuItem.deleted_at.is_(None),
                MenuItem.available.is_(True),
            )
        )
        waiting = await db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.sitting_id == sitting.id, Order.status == "pending_approval"
            )
        )
        if avg_price is not None:
            cap = avg_price * restaurant.first_order_cap_multiplier
            over_first_order_cap = waiting + total > cap

    if sitting is not None:
        # Last check before the order exists: code tries, allergen confirmations and refused
        # orders never use up a slot.
        await enforce_session_limit(str(session.id), "order_create", 3, 300, ORDERING_QUICKLY)

    order = Order(
        guest_session_id=session.id,
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        bill_id=bill.id if bill else None,
        sitting_id=sitting.id if sitting else None,
        status="awaiting_payment" if at_counter else "pending_approval" if pending else "placed",
        total=total,
        idempotency_key=payload.idempotency_key,
        payload_hash=payload_hash,
        allergen_conflict_acknowledged=ack_recorded,
        allergens_to_avoid=list(session.allergens_to_avoid),
        dietary_preferences=list(session.dietary_preferences),
        items=order_items,
    )

    # 7. Commit with concurrent duplicate protection
    try:
        db.add(order)
        await db.flush()

        # Write audit log for conflict acknowledgment if applicable
        if ack_recorded:
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
        if not is_idempotency_unique_violation(err):
            raise err

        # Query existing order created by concurrent thread
        res_conc = await db.execute(stmt_existing)
        conc_order = res_conc.scalar_one_or_none()
        if conc_order is not None and conc_order.payload_hash == payload_hash:
            response.status_code = status.HTTP_200_OK
            return await order_response(db, conc_order)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order conflict",
        ) from err

    # Re-fetch order with items eager-loaded
    res_final = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    final_order = res_final.scalar_one()

    # 8. Publish Redis change signal AFTER commit (publish failures never fail the order).
    # A counter order reaches the kitchen only when its bill is settled, a waiting one when
    # the waiter approves it.
    if final_order.status == "placed":
        order_event = json.dumps({"event": "order_placed", "order_id": str(final_order.id)})
        await publish_event(f"kitchen:{final_order.restaurant_id}", order_event)
        await publish_event(f"orders:{final_order.id}", order_event)
    elif final_order.status == "pending_approval":
        await publish_event(
            f"kitchen:{final_order.restaurant_id}",
            json.dumps({"event": "approval_needed", "table_id": str(final_order.table_id)}),
        )
        await publish_event(
            f"orders:{final_order.id}",
            json.dumps({"event": "order_pending_approval", "order_id": str(final_order.id)}),
        )
    if bill_created:
        await publish_event(
            f"kitchen:{final_order.restaurant_id}",
            json.dumps({"event": "bill_opened", "bill_id": str(final_order.bill_id)}),
        )

    response.status_code = status.HTTP_201_CREATED
    return await order_response(db, final_order, over_first_order_cap)


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
) -> OrderResponse:
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
    return await order_response(db, order)


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
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
