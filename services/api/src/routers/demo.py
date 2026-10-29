"""Demo router for public demo information and onboarding."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.dining_table import DiningTable
from src.models.restaurant import Restaurant
from src.schemas.auth import DemoInfoResponse, DemoVenueInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get(
    "/info",
    response_model=DemoInfoResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"description": "Demo mode disabled"}},
)
async def get_demo_info(
    db: AsyncSession = Depends(get_db),
) -> DemoInfoResponse:
    """Return live links for demo guest table, owner dashboard, and kitchen display.

    Returns 404 if DEMO_MODE is false.
    """
    if not settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled",
        )

    res = await db.execute(
        select(Restaurant, DiningTable)
        .join(DiningTable, DiningTable.restaurant_id == Restaurant.id)
        .where(Restaurant.slug.in_(settings.demo_restaurant_slugs), DiningTable.kind == "table")
        .order_by(Restaurant.slug, DiningTable.label)
    )
    first_table: dict[str, tuple[Restaurant, DiningTable]] = {}
    for restaurant, table in res.all():
        first_table.setdefault(restaurant.slug, (restaurant, table))

    venues = [
        DemoVenueInfo(
            slug=restaurant.slug,
            name=restaurant.name,
            city=restaurant.city,
            guest_url=f"{settings.public_guest_url}/q/{table.qr_token}",
            qr_token=table.qr_token,
            table_label=table.label,
        )
        for slug in settings.demo_restaurant_slugs
        if (pair := first_table.get(slug)) is not None
        for restaurant, table in [pair]
    ]
    return DemoInfoResponse(
        owner_url=settings.public_owner_url,
        kitchen_url=f"{settings.public_owner_url}/kitchen",
        venues=venues,
    )
