"""Demo router for public demo information and onboarding."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.dining_table import DiningTable
from src.models.restaurant import Restaurant
from src.schemas.auth import DemoInfoResponse

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

    stmt = (
        select(DiningTable)
        .join(Restaurant)
        .where(Restaurant.slug == settings.demo_restaurant_slug)
        .order_by(DiningTable.label)
        .limit(1)
    )
    res = await db.execute(stmt)
    table = res.scalar_one_or_none()

    guest_url = (
        f"{settings.public_guest_url}/q/{table.qr_token}"
        if table
        else f"{settings.public_guest_url}/q/demo"
    )

    return DemoInfoResponse(
        guest_url=guest_url,
        owner_url=settings.public_owner_url,
        kitchen_url=f"{settings.public_owner_url}/kitchen",
        qr_token=table.qr_token if table else "demo",
        table_label=table.label if table else "Table 1",
    )
