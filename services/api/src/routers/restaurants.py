"""The signed-in user's restaurants (venue switcher)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.access import get_current_user
from src.database import get_db
from src.models.restaurant import Restaurant
from src.models.user import Membership, User
from src.schemas.restaurants import MyRestaurant, MyRestaurantsResponse

router = APIRouter(tags=["restaurants"])


@router.get(
    "/api/restaurants",
    response_model=MyRestaurantsResponse,
    status_code=status.HTTP_200_OK,
    responses={401: {"description": "Unauthenticated"}},
)
async def list_my_restaurants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyRestaurantsResponse:
    """List the restaurants the signed-in user is a member of, with their role in each."""
    rows = await db.execute(
        select(Restaurant, Membership.role)
        .join(Membership, Membership.restaurant_id == Restaurant.id)
        .where(Membership.user_id == user.id)
        .order_by(Restaurant.name)
    )
    return MyRestaurantsResponse(
        restaurants=[
            MyRestaurant(
                slug=r.slug,
                name=r.name,
                city=r.city,
                currency=r.currency,
                role=role,
            )
            for r, role in rows.all()
        ]
    )
