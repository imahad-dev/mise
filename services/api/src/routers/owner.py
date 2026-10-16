"""Owner router for menu items and table management."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import Role, require_owner
from src.config import settings
from src.database import get_db
from src.models.audit import AuditLog
from src.models.dining_table import DiningTable
from src.models.menu import MenuItem
from src.models.restaurant import Restaurant
from src.schemas.owner import (
    OwnerMenuItemResponse,
    OwnerMenuTranslation,
    OwnerTableResponse,
    PatchMenuItemRequest,
    StatusOkResponse,
)

router = APIRouter(prefix="/api/restaurants/{slug}", tags=["owner"])


async def _get_restaurant(slug: str, db: AsyncSession) -> Restaurant:
    stmt = select(Restaurant).where(Restaurant.slug == slug)
    res = await db.execute(stmt)
    restaurant = res.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Restaurant '{slug}' not found",
        )
    return restaurant


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
    slug: str,
    role: Role = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> list[OwnerMenuItemResponse]:
    """List all non-deleted menu items for the restaurant, including unit_cost."""
    restaurant = await _get_restaurant(slug, db)

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
    slug: str,
    id: uuid.UUID,
    payload: PatchMenuItemRequest,
    role: Role = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> OwnerMenuItemResponse:
    """Update menu item fields.

    Changing allergens or ingredients sets allergen_verified=False with audit log.
    Changing dietary flags sets dietary_verified=False with audit log.
    """
    restaurant = await _get_restaurant(slug, db)

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
            actor="owner",
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
            actor="owner",
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
    slug: str,
    id: uuid.UUID,
    role: Role = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> OwnerMenuItemResponse:
    """Mark menu item as verified for both allergens and dietary preferences with audit log."""
    restaurant = await _get_restaurant(slug, db)

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
        actor="owner",
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
    slug: str,
    id: uuid.UUID,
    role: Role = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> StatusOkResponse:
    """Soft delete a menu item with audit log."""
    restaurant = await _get_restaurant(slug, db)

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
        actor="owner",
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
    slug: str,
    role: Role = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> list[OwnerTableResponse]:
    """List tables with label, qr_token, and full guest URL built from PUBLIC_GUEST_URL."""
    restaurant = await _get_restaurant(slug, db)

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
        )
        for t in tables
    ]
