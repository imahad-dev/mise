import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.access import RestaurantAccess, owner_access
from src.config import settings
from src.database import get_db
from src.inference.client import (
    InferenceClient,
    get_inference_client,
    get_optional_inference_client,
)
from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem, MenuItemOption
from src.redis_client import redis_client
from src.request_limits import enforce_ip_limit
from src.schemas.owner import (
    DailyBriefResponse,
    MenuIngestRequest,
    MenuIngestResponse,
    OwnerMenuItemResponse,
    OwnerMenuTranslation,
    OwnerTableResponse,
    PatchMenuItemRequest,
    PatchSettingsRequest,
    SettingsResponse,
    SimulateOrdersRequest,
    SimulateOrdersResponse,
    StatusOkResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from src.services.brief import compute_brief, compute_whatif
from src.services.menu_ingest import ingest_menu_from_image
from src.services.payment_details import PaymentDetailsError, validate_payment_details
from src.services.simulator import SimAssumptions, persist_simulation

router = APIRouter(prefix="/api/restaurants/{slug}", tags=["owner"])
logger = logging.getLogger(__name__)


def _build_owner_item_response(item: MenuItem) -> OwnerMenuItemResponse:
    translations = [
        OwnerMenuTranslation(
            language=t.language,
            name=t.name,
            description=t.description,
        )
        for t in item.translations
    ]
    return OwnerMenuItemResponse(
        id=item.id,
        restaurant_id=item.restaurant_id,
        category=item.category,
        price=item.price,
        unit_cost=item.unit_cost,
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
        translations=translations,
        deleted_at=item.deleted_at,
    )


@router.get(
    "/menu-items",
    response_model=list[OwnerMenuItemResponse],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
    },
)
async def list_owner_menu_items(
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> list[OwnerMenuItemResponse]:
    """List all non-deleted menu items for the restaurant, including unit_cost."""
    restaurant = access.restaurant

    stmt = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.deleted_at.is_(None),
        )
        .order_by(MenuItem.sort_order, MenuItem.category)
    )
    res = await db.execute(stmt)
    items = list(res.scalars().all())
    return [_build_owner_item_response(item) for item in items]


@router.patch(
    "/menu-items/{id}",
    response_model=OwnerMenuItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Menu item not found"},
    },
)
async def patch_menu_item(
    id: uuid.UUID,
    payload: PatchMenuItemRequest,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerMenuItemResponse:
    """Update menu item fields.

    Changing allergens or ingredients sets allergen_verified=False with audit log.
    Changing dietary flags sets dietary_verified=False with audit log.
    """
    restaurant = access.restaurant

    stmt = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(
            MenuItem.id == id,
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.deleted_at.is_(None),
        )
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

    if payload.price is not None or payload.unit_cost is not None:
        has_options = await db.scalar(
            select(MenuItemOption.id).where(MenuItemOption.menu_item_id == item.id).limit(1)
        )
        if has_options is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Edit the size prices instead",
            )

    if payload.price is not None:
        item.price = payload.price
    if payload.unit_cost is not None:
        item.unit_cost = payload.unit_cost
    if payload.available is not None:
        item.available = payload.available
    if payload.featured is not None:
        item.featured = payload.featured
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order

    # Check allergen/ingredient modifications
    allergen_changed = payload.allergens is not None and list(payload.allergens) != list(
        item.allergens
    )
    ingr_changed = payload.ingredients is not None and list(payload.ingredients) != list(
        item.ingredients
    )

    if allergen_changed or ingr_changed:
        before_snap = {"allergens": list(item.allergens), "ingredients": list(item.ingredients)}
        if payload.allergens is not None:
            item.allergens = list(payload.allergens)
        if payload.ingredients is not None:
            item.ingredients = list(payload.ingredients)
        item.allergen_verified = False
        after_snap = {"allergens": list(item.allergens), "ingredients": list(item.ingredients)}

        audit_all = AuditLog(
            restaurant_id=restaurant.id,
            event_type="owner_allergen_edit",
            actor=f"user:{access.user.id}",
            payload={"menu_item_id": str(item.id), "before": before_snap, "after": after_snap},
        )
        db.add(audit_all)

    # Check dietary modifications
    veg_changed = payload.is_vegetarian is not None and payload.is_vegetarian != item.is_vegetarian
    vegan_changed = payload.is_vegan is not None and payload.is_vegan != item.is_vegan
    gf_changed = (
        payload.is_gluten_free is not None and payload.is_gluten_free != item.is_gluten_free
    )

    if veg_changed or vegan_changed or gf_changed:
        before_diet = {
            "is_vegetarian": item.is_vegetarian,
            "is_vegan": item.is_vegan,
            "is_gluten_free": item.is_gluten_free,
        }
        if payload.is_vegetarian is not None:
            item.is_vegetarian = payload.is_vegetarian
        if payload.is_vegan is not None:
            item.is_vegan = payload.is_vegan
        if payload.is_gluten_free is not None:
            item.is_gluten_free = payload.is_gluten_free
        item.dietary_verified = False
        after_diet = {
            "is_vegetarian": item.is_vegetarian,
            "is_vegan": item.is_vegan,
            "is_gluten_free": item.is_gluten_free,
        }

        audit_diet = AuditLog(
            restaurant_id=restaurant.id,
            event_type="owner_dietary_edit",
            actor=f"user:{access.user.id}",
            payload={"menu_item_id": str(item.id), "before": before_diet, "after": after_diet},
        )
        db.add(audit_diet)

    await db.commit()
    res_item = await db.execute(
        select(MenuItem).options(selectinload(MenuItem.translations)).where(MenuItem.id == item.id)
    )
    item = res_item.scalar_one()
    return _build_owner_item_response(item)


@router.post(
    "/menu-items/{id}/verify",
    response_model=OwnerMenuItemResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Menu item not found"},
    },
)
async def verify_menu_item(
    id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> OwnerMenuItemResponse:
    """Mark menu item as verified for both allergens and dietary preferences with audit log."""
    restaurant = access.restaurant

    stmt = (
        select(MenuItem)
        .options(selectinload(MenuItem.translations))
        .where(
            MenuItem.id == id,
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.deleted_at.is_(None),
        )
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

    item.allergen_verified = True
    item.dietary_verified = True

    audit = AuditLog(
        restaurant_id=restaurant.id,
        event_type="owner_menu_verified",
        actor=f"user:{access.user.id}",
        payload={"menu_item_id": str(item.id)},
    )
    db.add(audit)
    await db.commit()
    res_item = await db.execute(
        select(MenuItem).options(selectinload(MenuItem.translations)).where(MenuItem.id == item.id)
    )
    item = res_item.scalar_one()
    return _build_owner_item_response(item)


@router.delete(
    "/menu-items/{id}",
    response_model=StatusOkResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Menu item not found"},
    },
)
async def delete_menu_item(
    id: uuid.UUID,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    """Soft delete a menu item with audit log."""
    restaurant = access.restaurant

    stmt = select(MenuItem).where(
        MenuItem.id == id,
        MenuItem.restaurant_id == restaurant.id,
        MenuItem.deleted_at.is_(None),
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

    now = datetime.now(UTC)
    item.deleted_at = now

    audit = AuditLog(
        restaurant_id=restaurant.id,
        event_type="menu_item_deleted",
        actor=f"user:{access.user.id}",
        payload={"menu_item_id": str(item.id), "deleted_at": str(now)},
    )
    db.add(audit)
    await db.commit()
    return StatusOkResponse(status="ok")


@router.get(
    "/tables",
    response_model=list[OwnerTableResponse],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
    },
)
async def list_tables(
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> list[OwnerTableResponse]:
    """List tables with label, qr_token, and full guest URL built from PUBLIC_GUEST_URL."""
    restaurant = access.restaurant

    stmt = (
        select(DiningTable)
        .where(DiningTable.restaurant_id == restaurant.id)
        .order_by(DiningTable.label)
    )
    res = await db.execute(stmt)
    tables = list(res.scalars().all())

    base_url = settings.public_guest_url.rstrip("/")
    return [
        OwnerTableResponse(
            id=t.id,
            restaurant_id=t.restaurant_id,
            label=t.label,
            qr_token=t.qr_token,
            guest_url=f"{base_url}/q/{t.qr_token}",
            kind=t.kind,
        )
        for t in tables
    ]


@router.get(
    "/settings",
    response_model=SettingsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
    },
)
async def get_settings(access: RestaurantAccess = Depends(owner_access)) -> SettingsResponse:
    r = access.restaurant
    return SettingsResponse(
        payment_details=r.payment_details,
        service_extra_label=r.service_extra_label,
        pickup_prefix=r.pickup_prefix,
    )


@router.patch(
    "/settings",
    response_model=SettingsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
        409: {"description": "Pickup prefix changed while counter orders are open"},
        422: {"description": "Invalid setting; detail.field names it"},
    },
)
async def patch_settings(
    payload: PatchSettingsRequest,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Update payment details, the extra call reason and the pickup prefix.

    Omitted fields stay as they are; a given `payment_details` replaces the whole object;
    `pickup_prefix: null` clears the prefix (pickup numbers then print K-…);
    `service_extra_label: null` or "" clears the extra call reason.
    """
    restaurant = access.restaurant
    if payload.payment_details is not None:
        raw = dict(payload.payment_details)
        is_demo = settings.demo_mode and restaurant.slug in settings.demo_restaurant_slugs
        if is_demo:
            raw["sample"] = True  # demo venues can never show real-looking payment details
        try:
            cleaned = validate_payment_details(raw, allow_sample=is_demo)
        except PaymentDetailsError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"field": e.field, "message": e.message},
            ) from e
        db.add(
            AuditLog(
                restaurant_id=restaurant.id,
                event_type="owner_payment_details_edit",
                actor=f"user:{access.user.id}",
                payload={"before": restaurant.payment_details, "after": cleaned},
            )
        )
        restaurant.payment_details = cleaned
    if "service_extra_label" in payload.model_fields_set:
        restaurant.service_extra_label = payload.service_extra_label
    if (
        "pickup_prefix" in payload.model_fields_set
        and payload.pickup_prefix != restaurant.pickup_prefix
    ):
        # Guests already hold a printed number: it must not change under them. The bill-numbering
        # lock keeps a counter order from opening between this check and the commit.
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bill:{restaurant.id}"))))
        if await db.scalar(
            select(
                exists().where(
                    Bill.restaurant_id == restaurant.id,
                    Bill.pickup_no.is_not(None),
                    Bill.status == "open",
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Finish open counter orders before changing the prefix",
            )
        restaurant.pickup_prefix = payload.pickup_prefix
    await db.commit()
    return SettingsResponse(
        payment_details=restaurant.payment_details,
        service_extra_label=restaurant.service_extra_label,
        pickup_prefix=restaurant.pickup_prefix,
    )


# --- Checkpoint D: AI endpoints ---


@router.post(
    "/menu-items/ingest",
    response_model=MenuIngestResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
        429: {"description": "Demo mode limit reached (max 3 per hour per IP)"},
    },
)
async def ingest_menu(
    payload: MenuIngestRequest,
    request: Request,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
    inference: InferenceClient = Depends(get_inference_client),
) -> MenuIngestResponse:
    """Analyze a menu photo via VLM and create menu items automatically."""
    restaurant = access.restaurant

    if settings.demo_mode:
        await enforce_ip_limit(
            request,
            "demo:ingest",
            limit=3,
            window_s=3600,
            detail="Demo limit reached: maximum 3 menu ingestions per hour per IP",
        )

    created_items = await ingest_menu_from_image(
        inference=inference,
        db=db,
        restaurant_id=restaurant.id,
        image_url=payload.image_url,
        language=payload.language,
    )

    return MenuIngestResponse(
        created_count=len(created_items),
        items=[_build_owner_item_response(item) for item in created_items],
    )


@router.get(
    "/ai/brief",
    response_model=DailyBriefResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
    },
)
async def daily_brief(
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
    inference: InferenceClient | None = Depends(get_optional_inference_client),
) -> DailyBriefResponse:
    """Deterministic analytics brief; the LLM only narrates. Cached for 10m in DEMO_MODE."""
    restaurant = access.restaurant
    cache_key = f"cache:demo:brief:v4:{restaurant.slug}"

    if settings.demo_mode:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return DailyBriefResponse.model_validate_json(cached)
        except Exception as e:
            logger.warning("Redis error reading brief cache: %s", e)

    brief_resp = DailyBriefResponse(**await compute_brief(db, restaurant, inference))

    if settings.demo_mode:
        try:
            await redis_client.set(cache_key, brief_resp.model_dump_json(), ex=600)
        except Exception as e:
            logger.warning("Redis error writing brief cache: %s", e)

    return brief_resp


@router.post(
    "/ai/simulate",
    response_model=WhatIfResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Restaurant not found"},
        422: {"description": "Invalid scenario parameters"},
    },
)
async def simulate(
    payload: WhatIfRequest,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
    inference: InferenceClient | None = Depends(get_optional_inference_client),
) -> WhatIfResponse:
    """Deterministic what-if calculator; the LLM may only explain the result."""
    restaurant = access.restaurant
    params = payload.model_dump(exclude_none=True, exclude={"scenario"}, mode="json")
    try:
        result = await compute_whatif(db, restaurant, inference, payload.scenario, params)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return WhatIfResponse(**result)


def _require_demo_venue(access: RestaurantAccess) -> None:
    """Demo data tools exist only in DEMO_MODE and only for the configured demo venues."""
    if not settings.demo_mode or access.restaurant.slug not in settings.demo_restaurant_slugs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is disabled")


@router.post(
    "/demo/simulate-orders",
    response_model=SimulateOrdersResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Demo mode disabled or restaurant not found"},
        429: {"description": "Demo limit reached (max 3 per hour per IP)"},
    },
)
async def simulate_demo_orders(
    payload: SimulateOrdersRequest,
    request: Request,
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> SimulateOrdersResponse:
    """Replace source='simulated' orders with a seeded synthetic history. DEMO_MODE only."""
    _require_demo_venue(access)
    await enforce_ip_limit(
        request,
        "demo:simulate",
        limit=3,
        window_s=3600,
        detail="Demo limit reached: maximum 3 demo data generations per hour per IP",
    )
    restaurant = access.restaurant
    base = SimAssumptions.from_profile(restaurant.onboarding.get("simulation", {}))
    assumptions = replace(
        base,
        days=payload.days,
        seed=payload.seed,
        promo_item_rank=base.promo_item_rank if payload.promotion else None,
    )
    summary = await persist_simulation(db, restaurant, assumptions)
    await db.commit()
    try:
        await redis_client.delete(f"cache:demo:brief:v4:{restaurant.slug}")
    except Exception as e:
        logger.warning("Redis error clearing brief cache: %s", e)
    return SimulateOrdersResponse(**summary)


@router.post(
    "/demo/reset",
    response_model=StatusOkResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated"},
        403: {"description": "Unauthorized (Owner only)"},
        404: {"description": "Demo mode disabled or restaurant not found"},
    },
)
async def reset_demo_data(
    access: RestaurantAccess = Depends(owner_access),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    """Re-seed restaurant data and regenerate simulated state. DEMO_MODE only."""
    _require_demo_venue(access)

    from scripts.seed import find_seed_for_slug, seed_data

    # Only this venue's own seed: an owner can never re-seed another restaurant.
    data = find_seed_for_slug(access.restaurant.slug)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No demo seed for this restaurant"
        )

    try:
        await seed_data(data, db, rotate_qr=False)
        await db.commit()
    except Exception as e:
        logger.error("Failed to reset demo data: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset demo data: {e}",
        ) from e

    return StatusOkResponse(status="ok")
