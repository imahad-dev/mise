"""Guest session management, guest menu, and AI chat endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_guest_session, set_guest_cookie
from src.database import get_db
from src.inference.client import InferenceClient, get_inference_client
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.schemas.guest import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateGuestSessionRequest,
    GuestMenuItemResponse,
    GuestMenuResponse,
    GuestSessionResponse,
    PatchGuestSessionRequest,
)
from src.services.allergen_service import compute_allergen_status
from src.services.guest_chat import handle_guest_chat

router = APIRouter(prefix="/api/guest", tags=["guest"])


@router.post(
    "/sessions",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Unknown QR token"}},
)
async def create_guest_session(
    payload: CreateGuestSessionRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> GuestSessionResponse:
    """Create a guest session by scanning a dining table QR code.

    Sets a 4-hour signed httpOnly mise_guest cookie.
    """
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
    )
    db.add(guest_session)
    await db.commit()
    await db.refresh(guest_session)

    set_guest_cookie(response, guest_session.id)
    return GuestSessionResponse.model_validate(guest_session)


@router.get(
    "/session",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated or expired session"}},
)
async def get_guest_session(
    session: GuestSession = Depends(get_current_guest_session),
) -> GuestSessionResponse:
    """Retrieve details for the active guest session."""
    return GuestSessionResponse.model_validate(session)


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
        .options(selectinload(MenuItem.translations))
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
                available=item.available,
                featured=item.featured,
                sort_order=item.sort_order,
                image_url=item.image_url,
                allergen_status=status_val,
                matched_allergens=matched_allergens,
            )
        )

    return GuestMenuResponse(items=menu_responses)


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
        guest_allergens=list(session.allergens_to_avoid),
        guest_dietary=list(session.dietary_preferences),
        message=payload.message,
    )

    return ChatMessageResponse(
        reply=result.get("reply", ""),
        suggested_items=result.get("suggested_items", []),
    )
