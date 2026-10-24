"""Signed-in user and per-restaurant access. Non-members get 404, never 403."""

import time
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, Role, unsign_value
from src.database import get_db
from src.models.restaurant import Restaurant
from src.models.user import Membership, User

NOT_FOUND = "Restaurant not found"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        raise _unauthorized("Authentication required")
    val = unsign_value(cookie)
    if not val or ":" not in val:
        raise _unauthorized("Invalid authentication cookie")
    uid_str, exp_str = val.split(":", 1)
    try:
        user_id = uuid.UUID(uid_str)
        expired = time.time() > int(exp_str)
    except ValueError:
        raise _unauthorized("Malformed authentication cookie") from None
    if expired:
        raise _unauthorized("Authentication cookie expired")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise _unauthorized("Unknown user")
    return user


@dataclass(frozen=True)
class RestaurantAccess:
    restaurant: Restaurant
    user: User
    role: Role


def restaurant_access(*roles: Role):
    """Dependency: the path's {slug} restaurant, if the user is a member with one of roles."""
    allowed = set(roles or ("owner", "staff"))

    async def dependency(
        slug: str,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> RestaurantAccess:
        row = (
            await db.execute(
                select(Restaurant, Membership.role)
                .join(Membership, Membership.restaurant_id == Restaurant.id)
                .where(Restaurant.slug == slug, Membership.user_id == user.id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
        restaurant, role = row
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Owner privileges required"
            )
        return RestaurantAccess(restaurant=restaurant, user=user, role=role)

    return dependency


owner_access = restaurant_access("owner")
member_access = restaurant_access("owner", "staff")
