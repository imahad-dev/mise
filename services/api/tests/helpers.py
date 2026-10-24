"""Test helpers: create users with memberships and sign them in."""

import time
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.models.user import Membership, User
from src.passwords import hash_password


async def make_user(
    db: AsyncSession,
    memberships: list[tuple[uuid.UUID, str]],
    email: str | None = None,
    password: str = "pw-for-tests",
) -> User:
    user = User(
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        name="Test user",
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    for restaurant_id, role in memberships:
        db.add(Membership(user_id=user.id, restaurant_id=restaurant_id, role=role))
    await db.flush()
    return user


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, sign_value(f"{user.id}:{int(time.time()) + 3600}"))


async def as_member(
    client: AsyncClient, db: AsyncSession, restaurant_id: uuid.UUID, role: str
) -> User:
    user = await make_user(db, [(restaurant_id, role)])
    sign_in(client, user)
    return user
