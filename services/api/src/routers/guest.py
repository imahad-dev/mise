"""Guest session management, guest menu, AI chat and bill endpoints."""

import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_guest_session, set_guest_cookie
from src.database import get_db
from src.inference.client import InferenceClient, get_inference_client
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuChoice, MenuChoiceGroup, MenuItem
from src.models.order import Order
from src.models.pay_forward import PayForward
from src.models.restaurant import Restaurant
from src.models.service_call import ServiceCall
from src.models.session import GuestSession
from src.models.sitting import TableSitting
from src.redis_client import publish_event
from src.request_limits import enforce_ip_limit
from src.schemas.bills import GuestBillResponse
from src.schemas.floor import (
    CurrentCallResponse,
    ServiceCallRequest,
    ServiceCallResponse,
    call_response,
)
from src.schemas.guest import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateGuestSessionRequest,
    GuestMenuChoice,
    GuestMenuChoiceGroup,
    GuestMenuItemResponse,
    GuestMenuOption,
    GuestMenuResponse,
    GuestMenuRestaurant,
    GuestSessionResponse,
    GuestSessionStatusResponse,
    PatchGuestSessionRequest,
)
from src.schemas.payments import (
    GuestBillDetail,
    GuestPaymentRequest,
    PaymentDetails,
    VoidedLine,
)
from src.services.allergen_service import compute_allergen_status
from src.services.bills import (
    METHOD_REFUSED,
    VISIT_ENDED,
    active_orders,
    bill_lines,
    bill_service,
    claim_of,
    is_expired_unpaid,
    local_date,
    method_preview,
    method_previews,
    revive_expired,
    session_is_current,
    session_started_at,
)
from src.services.choices import can_be_ordered
from src.services.counter import order_status as counter_order_status
from src.services.counter import pickup_label
from src.services.guest_chat import handle_guest_chat
from src.services.tax import jurisdiction_of, methods_for, service_charge_for

router = APIRouter(prefix="/api/guest", tags=["guest"])


@router.post(
    "/sessions",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Unknown QR token"},
        429: {"description": "Too many new sessions from this address"},
    },
)
async def create_guest_session(
    payload: CreateGuestSessionRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> GuestSessionResponse:
    """Create a guest session by scanning a dining table QR code.

    Sets a 4-hour signed httpOnly mise_guest cookie.
    """
    # Each new session gets fresh table-code tries. Generous: a whole venue's guests may share
    # one Wi-Fi address.
    await enforce_ip_limit(
        request, "guest_session", 60, 600, "Please ask your waiter to help you order."
    )
    stmt_table = select(DiningTable).where(DiningTable.qr_token == payload.qr_token)
    res_table = await db.execute(stmt_table)
    table = res_table.scalar_one_or_none()

    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown QR token",
        )

    expires_at = datetime.now(UTC) + timedelta(hours=4)
    guest_session = GuestSession(
        restaurant_id=table.restaurant_id,
        table_id=table.id,
        language=payload.language,
        dietary_preferences=list(payload.dietary_preferences),
        allergens_to_avoid=list(payload.allergens_to_avoid),
        expires_at=expires_at,
        created_at=await session_started_at(db, table.id),
    )
    db.add(guest_session)
    await db.commit()
    await db.refresh(guest_session)

    set_guest_cookie(response, guest_session.id)
    return GuestSessionResponse.model_validate(guest_session)


@router.get(
    "/session",
    response_model=GuestSessionStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated or expired session"}},
)
async def get_guest_session(
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestSessionStatusResponse:
    """The active guest session, and whether its table is open for this phone to order.

    A plain read, by the same rules create_order uses: a counter needs no sitting; a phone bound to
    an earlier sitting must scan again; the code is asked once per phone per sitting.
    """
    table_state, code_required = "open", False
    kind = await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
    if session.table_id is not None and kind != "counter":
        sitting = (
            await db.execute(
                select(TableSitting.id, TableSitting.code_required).where(
                    TableSitting.table_id == session.table_id, TableSitting.closed_at.is_(None)
                )
            )
        ).one_or_none()
        if session.sitting_id is not None and (sitting is None or session.sitting_id != sitting.id):
            table_state = "closed"  # it ordered on a visit that has ended (one open per table)
        elif not await session_is_current(db, session):
            table_state = "ended"  # a phone left from the last party
        elif sitting is None:
            table_state = "waiting"
        else:
            code_required = sitting.code_required and session.sitting_id is None
    return GuestSessionStatusResponse(
        **GuestSessionResponse.model_validate(session).model_dump(),
        table_state=table_state,
        code_required=code_required,
    )


@router.patch(
    "/session",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated or expired session"}},
)
async def patch_guest_session(
    payload: PatchGuestSessionRequest,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestSessionResponse:
    """Update language, dietary preferences, or allergens to avoid for the session."""
    if payload.language is not None:
        session.language = payload.language
    if payload.dietary_preferences is not None:
        session.dietary_preferences = list(payload.dietary_preferences)
    if payload.allergens_to_avoid is not None:
        session.allergens_to_avoid = list(payload.allergens_to_avoid)

    await db.commit()
    await db.refresh(session)
    return GuestSessionResponse.model_validate(session)


def _guest_choice(c: MenuChoice, avoid: list[str]) -> GuestMenuChoice:
    status_val = compute_allergen_status(
        item_allergens=c.allergens,
        allergen_verified=c.allergen_verified,
        guest_allergens_to_avoid=avoid,
    )
    return GuestMenuChoice(
        id=c.id,
        label=c.label,
        price_delta=c.price_delta,
        allergens=c.allergens,
        is_vegetarian=c.is_vegetarian,
        is_vegan=c.is_vegan,
        available=c.available,
        is_default=c.is_default,
        allergen_status=status_val,
        matched_allergens=[a for a in c.allergens if a in avoid]
        if status_val == "contains"
        else [],
    )


@router.get(
    "/menu",
    response_model=GuestMenuResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated or expired session"}},
)
async def get_guest_menu(
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestMenuResponse:
    """Return the restaurant menu customized for the guest session.

    - Translation matches session language with fallback to restaurant default language.
    - Excludes deleted items.
    - Available items shown; unavailable included with available=False.
    - Computes allergen_status and matched_allergens.
    - NEVER includes unit_cost.
    """
    # 1. Fetch restaurant default language
    stmt_rest = select(Restaurant).where(Restaurant.id == session.restaurant_id)
    res_rest = await db.execute(stmt_rest)
    restaurant = res_rest.scalar_one()

    # 2. Fetch active menu items with eager loaded translations
    stmt_items = (
        select(MenuItem)
        .options(
            selectinload(MenuItem.translations),
            selectinload(MenuItem.options),
            selectinload(MenuItem.choice_groups).selectinload(MenuChoiceGroup.choices),
        )
        .where(
            MenuItem.restaurant_id == session.restaurant_id,
            MenuItem.deleted_at.is_(None),
        )
        .order_by(MenuItem.sort_order, MenuItem.category)
    )
    res_items = await db.execute(stmt_items)
    items = list(res_items.scalars().all())

    menu_responses: list[GuestMenuItemResponse] = []
    for item in items:
        # Match translation
        trans_by_lang = {t.language: t for t in item.translations}
        selected_trans = trans_by_lang.get(session.language) or trans_by_lang.get(
            restaurant.default_language
        )
        if selected_trans is None and trans_by_lang:
            selected_trans = next(iter(trans_by_lang.values()))

        name = selected_trans.name if selected_trans else ""
        description = selected_trans.description if selected_trans else None

        # Compute allergen status
        status_val = compute_allergen_status(
            item_allergens=item.allergens,
            allergen_verified=item.allergen_verified,
            guest_allergens_to_avoid=session.allergens_to_avoid,
        )
        matched_allergens = (
            [a for a in item.allergens if a in session.allergens_to_avoid]
            if status_val == "contains"
            else []
        )

        menu_responses.append(
            GuestMenuItemResponse(
                id=item.id,
                category=item.category,
                price=item.price,
                name=name,
                description=description,
                ingredients=item.ingredients,
                allergens=item.allergens,
                allergen_verified=item.allergen_verified,
                dietary_verified=item.dietary_verified,
                is_vegetarian=item.is_vegetarian,
                is_vegan=item.is_vegan,
                is_gluten_free=item.is_gluten_free,
                available=item.available and can_be_ordered(item),
                featured=item.featured,
                sort_order=item.sort_order,
                image_url=item.image_url,
                allergen_status=status_val,
                matched_allergens=matched_allergens,
                options=[
                    GuestMenuOption(id=o.id, label=o.label, price=o.price) for o in item.options
                ],
                choice_groups=[
                    GuestMenuChoiceGroup(
                        id=g.id,
                        label=g.label,
                        kind=g.kind,
                        min_select=g.min_select,
                        max_select=g.max_select,
                        choices=[_guest_choice(c, session.allergens_to_avoid) for c in g.choices],
                    )
                    for g in item.choice_groups
                ],
            )
        )

    table_label = table_kind = None
    if session.table_id is not None:
        row = (
            await db.execute(
                select(DiningTable.label, DiningTable.kind).where(
                    DiningTable.id == session.table_id
                )
            )
        ).one_or_none()
        if row is not None:
            table_label, table_kind = row

    jurisdiction = jurisdiction_of(restaurant.tax_jurisdiction)
    return GuestMenuResponse(
        restaurant=GuestMenuRestaurant(
            id=restaurant.id,
            name=restaurant.name,
            currency=restaurant.currency,
            # The rate applies to table bills only; counter phones see the notice too.
            service_charge_rate=service_charge_for(
                restaurant.tax_jurisdiction, restaurant.service_charge_rate, Decimal(0), True
            )[0],
            prices_include_tax=jurisdiction is not None and jurisdiction.pricing == "included",
        ),
        table_id=session.table_id,
        table_label=table_label,
        table_kind=table_kind,
        service_extra_label=restaurant.service_extra_label,
        items=menu_responses,
    )


# --- Checkpoint D: Guest Chat ---


@router.post(
    "/chat",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated or expired session"},
        429: {"description": "Chat message limit reached"},
    },
)
async def guest_chat(
    payload: ChatMessageRequest,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
    inference: InferenceClient = Depends(get_inference_client),
) -> ChatMessageResponse:
    """Send a chat message to the AI menu assistant.

    Rate limited to GUEST_CHAT_LIMIT messages per session.
    The server builds the menu context — client only displays the response.
    """
    result = await handle_guest_chat(
        inference=inference,
        db=db,
        restaurant_id=session.restaurant_id,
        session_id=session.id,
        guest_language=session.language,
        message=payload.message,
    )

    return ChatMessageResponse(
        reply=result.get("reply", ""),
        suggested_items=result.get("suggested_items", []),
    )


# --- Bills ---


@router.post(
    "/bill-request",
    response_model=GuestBillResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated or expired session"},
        404: {"description": "No open bill"},
    },
)
async def request_bill(
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestBillResponse:
    """Ask for the table's open bill. Idempotent: the first request time is kept."""
    bill = None
    if session.table_id is not None and await session_is_current(db, session):
        bill = (
            await db.execute(
                select(Bill)
                .where(
                    Bill.restaurant_id == session.restaurant_id,
                    Bill.table_id == session.table_id,
                    Bill.status == "open",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No open bill")
    if bill.bill_requested_at is None:
        bill.bill_requested_at = await db.scalar(select(func.clock_timestamp()))
    await db.commit()
    await publish_event(
        f"kitchen:{session.restaurant_id}",
        json.dumps({"event": "bill_requested", "bill_id": str(bill.id)}),
    )
    return GuestBillResponse(
        bill_no=bill.bill_no, status=bill.status, bill_requested_at=bill.bill_requested_at
    )


async def _session_bill(
    db: AsyncSession,
    session: GuestSession,
    *,
    lock: bool = False,
    order_id: uuid.UUID | None = None,
) -> Bill | None:
    """The bill of the given order of this session; else the open bill of the session's table,
    else the bill of its latest billed order."""
    if order_id is not None:
        # Each counter order has its own bill: the order page reads and pays that one only.
        query = (
            select(Bill)
            .join(Order, Order.bill_id == Bill.id)
            .where(Order.id == order_id, Order.guest_session_id == session.id)
        )
        if lock:
            query = query.with_for_update(of=Bill).execution_options(populate_existing=True)
        return (await db.execute(query)).scalar_one_or_none()
    if session.table_id is not None and await session_is_current(db, session):
        query = select(Bill).where(
            Bill.restaurant_id == session.restaurant_id,
            Bill.table_id == session.table_id,
            Bill.status == "open",
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        bill = (await db.execute(query)).scalar_one_or_none()
        if bill is not None:
            return bill
    # A stale session still sees its own (settled) bill, never the next party's.
    query = (
        select(Bill)
        .join(Order, Order.bill_id == Bill.id)
        .where(Order.guest_session_id == session.id)
        .order_by(Order.placed_at.desc(), Bill.opened_at.desc(), Bill.bill_no.desc())
        .limit(1)
    )
    if lock:
        # Re-read after the lock so the caller's status check sees a concurrent settle.
        query = query.with_for_update(of=Bill).execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def _bill_detail(
    db: AsyncSession, session: GuestSession, bill: Bill, restaurant: Restaurant
) -> GuestBillDetail:
    now = await db.scalar(select(func.clock_timestamp()))
    lines, subtotal = bill_lines(await active_orders(db, bill.id))
    voided_orders = list(
        (
            await db.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.bill_id == bill.id, Order.voided_at.is_not(None))
                .order_by(Order.placed_at, Order.id)
            )
        )
        .scalars()
        .all()
    )
    voided, _ = bill_lines(voided_orders)
    latest = (
        await db.execute(
            select(Order.status, Order.collected_at)
            .where(Order.bill_id == bill.id, Order.guest_session_id == session.id)
            .order_by(Order.placed_at.desc(), Order.id.desc())
            .limit(1)
        )
    ).one_or_none()
    order_status = counter_order_status(*latest) if latest else None
    is_open = bill.status == "open"
    sc_rate, sc_amount = (
        bill_service(restaurant, bill, subtotal)
        if is_open
        else (bill.service_charge_rate, bill.service_charge_amount)
    )
    return GuestBillDetail(
        bill_no=bill.bill_no,
        status=bill.status,
        bill_requested_at=bill.bill_requested_at,
        lines=lines,
        subtotal=subtotal if is_open or bill.subtotal is None else bill.subtotal,
        currency=restaurant.currency,
        methods=(
            method_previews(restaurant.tax_jurisdiction, subtotal, local_date(restaurant, now))
            if is_open
            else []
        ),
        service_charge_rate=sc_rate,
        service_charge_amount=sc_amount,
        payment_details=PaymentDetails(**restaurant.payment_details),
        claim=claim_of(bill),
        voided=[
            VoidedLine(
                name=v.name,
                option_label=v.option_label,
                quantity=v.quantity,
                choices=v.choices,
            )
            for v in voided
        ],
        order_status=order_status,
        payment_method=bill.payment_method if bill.status == "settled" else None,
        tax_rate=bill.tax_rate if bill.status == "settled" else None,
        tax_included=bill.status == "settled" and bill.tax_pricing == "included",
        total=bill.total if bill.status == "settled" else None,
        pickup_label=(
            pickup_label(restaurant.pickup_prefix, bill.pickup_no) if bill.pickup_no else None
        ),
        pay_forward_count=int(
            await db.scalar(
                select(func.coalesce(func.sum(PayForward.quantity), 0))
                .join(Order, Order.id == PayForward.order_id)
                .where(
                    Order.bill_id == bill.id,
                    # A shared table bill: thank each phone for its own chai only.
                    Order.guest_session_id == session.id,
                    PayForward.kind == "bought",
                )
            )
        ),
    )


@router.get(
    "/bill",
    response_model=GuestBillDetail,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated or expired session"},
        404: {"description": "No bill for this session"},
    },
)
async def get_guest_bill(
    order_id: uuid.UUID | None = None,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestBillDetail:
    """The table's open bill (else the session's latest bill): lines, per-method totals, claim.

    With order_id: the bill of that order of this session (404 for any other order).
    """
    bill = await _session_bill(db, session, order_id=order_id)
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bill")
    restaurant = await db.get(Restaurant, session.restaurant_id)
    return await _bill_detail(db, session, bill, restaurant)


@router.post(
    "/bill/payment",
    response_model=GuestBillDetail,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated or expired session"},
        404: {"description": "No bill for this session"},
        409: {"description": "Bill is no longer open"},
        422: {"description": "Invalid method or reference, no active orders, or no tax rate"},
    },
)
async def claim_payment(
    payload: GuestPaymentRequest,
    order_id: uuid.UUID | None = None,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> GuestBillDetail:
    """Record how the guest pays (counts as requesting the bill). Never settles; latest wins."""
    restaurant = await db.get(Restaurant, session.restaurant_id)
    if payload.method not in methods_for(restaurant.tax_jurisdiction):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=METHOD_REFUSED
        )
    # Locked: concurrent taps serialise here, so an identical repeat sees the stored claim.
    bill = await _session_bill(db, session, lock=True, order_id=order_id)
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bill")
    # A counter order that expired unpaid comes back when the guest says they paid.
    # Only on the day it was numbered; an older one needs staff (they can still settle it).
    revived = []
    if is_expired_unpaid(bill):
        now = await db.scalar(select(func.clock_timestamp()))
        if bill.pickup_day == local_date(restaurant, now):
            revived = await revive_expired(db, bill, session.restaurant_id, f"guest:{session.id}")
    if bill.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bill is not open")
    # Service is recorded only where this bill can carry it, so a repeat compares equal.
    include = payload.service_included and bill_service(restaurant, bill, Decimal(0))[0] > 0
    now = await db.scalar(select(func.clock_timestamp()))
    orders = await active_orders(db, bill.id)
    total = None
    if orders:
        _, subtotal = bill_lines(orders)
        preview = method_preview(
            restaurant.tax_jurisdiction, payload.method, subtotal, local_date(restaurant, now)
        )
        if preview is not None:
            _, sc_amount = bill_service(restaurant, bill, subtotal)
            total = preview.total + (sc_amount if include else 0)
    # A repeat after new orders refreshes the claimed total; an identical one changes nothing.
    changed = (
        bill.claimed_method,
        bill.claimed_reference,
        bill.claimed_service_included,
    ) != (payload.method, payload.reference, include) or (
        total is not None and bill.claimed_total != total
    )
    if changed:
        if not orders:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No active orders"
            )
        if total is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No tax rate configured"
            )
        bill.claimed_method = payload.method
        bill.claimed_reference = payload.reference
        bill.claimed_service_included = include
        bill.claimed_total = total
        bill.claimed_at = now
        if bill.bill_requested_at is None:
            bill.bill_requested_at = now
        db.add(
            AuditLog(
                restaurant_id=session.restaurant_id,
                event_type="payment_claimed",
                actor=f"guest:{session.id}",
                payload={
                    "bill_id": str(bill.id),
                    "method": payload.method,
                    "reference_last4": payload.reference[-4:] if payload.reference else None,
                    "service_included": include,
                    "total": str(bill.claimed_total),
                },
            )
        )
    await db.commit()
    for order_id in revived:
        await publish_event(
            f"orders:{order_id}", json.dumps({"event": "order_revived", "order_id": str(order_id)})
        )
    if changed:
        await publish_event(
            f"kitchen:{session.restaurant_id}",
            json.dumps({"event": "payment_claimed", "bill_id": str(bill.id)}),
        )
    return await _bill_detail(db, session, bill, restaurant)


# --- Call waiter ---

CALL_COOLDOWN = timedelta(seconds=60)


async def _extra_label(db: AsyncSession, session: GuestSession) -> str | None:
    return await db.scalar(
        select(Restaurant.service_extra_label).where(Restaurant.id == session.restaurant_id)
    )


@router.post(
    "/service-calls",
    response_model=ServiceCallResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Unauthenticated or expired session"},
        409: {"description": "A waiter is already on the way"},
        422: {"description": "Not a table session"},
        429: {"description": "Called less than 60 seconds ago"},
    },
)
async def create_service_call(
    payload: ServiceCallRequest,
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> ServiceCallResponse:
    """Call a waiter to the session's table. One open call per table, 60 s between calls."""
    kind = (
        await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
        if session.table_id is not None
        else None
    )
    if kind != "table":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Calling a waiter works only at a table",
        )
    if not await session_is_current(db, session):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=VISIT_ENDED)
    on_the_way = HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="A waiter is already on the way"
    )
    now = await db.scalar(select(func.clock_timestamp()))
    latest = (
        await db.execute(
            select(ServiceCall)
            .where(ServiceCall.table_id == session.table_id)
            .order_by(ServiceCall.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and latest.resolved_at is None:
        raise on_the_way
    if latest is not None and (wait := CALL_COOLDOWN - (now - latest.created_at)) > timedelta(0):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait a minute before calling again",
            headers={"Retry-After": str(math.ceil(wait.total_seconds()))},
        )
    call = ServiceCall(
        restaurant_id=session.restaurant_id,
        table_id=session.table_id,
        reason=payload.reason,
        created_at=now,
        resolved_at=None,
    )
    db.add(call)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # the partial unique index: a parallel call won
        raise on_the_way from None
    await publish_event(
        f"kitchen:{session.restaurant_id}",
        json.dumps(
            {
                "event": "service_call_opened",
                "call_id": str(call.id),
                "table_id": str(call.table_id),
            }
        ),
    )
    return call_response(call, await _extra_label(db, session))


@router.get(
    "/service-calls/current",
    response_model=CurrentCallResponse,
    responses={401: {"description": "Unauthenticated or expired session"}},
)
async def current_service_call(
    session: GuestSession = Depends(get_current_guest_session),
    db: AsyncSession = Depends(get_db),
) -> CurrentCallResponse:
    """The table's open call or null, whether calling is possible here, and the server clock."""
    now = await db.scalar(select(func.clock_timestamp()))
    extra = await _extra_label(db, session)
    kind = call = None
    if session.table_id is not None:
        kind = await db.scalar(select(DiningTable.kind).where(DiningTable.id == session.table_id))
        call = (
            await db.execute(
                select(ServiceCall).where(
                    ServiceCall.table_id == session.table_id, ServiceCall.resolved_at.is_(None)
                )
            )
        ).scalar_one_or_none()
    return CurrentCallResponse(
        call=call_response(call, extra) if call else None,
        available=kind == "table",
        extra_label=extra,
        server_time=now,
    )
