"""Test helpers: create users with memberships and sign them in; seat tables, approve orders."""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.database import get_db
from src.main import app
from src.models.order import Order
from src.models.sitting import TableSitting
from src.models.user import Membership, User
from src.passwords import hash_password
from src.services.sitting import approve_pending, get_open_sitting


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


async def settle(
    client: AsyncClient, slug: str, bill_id: uuid.UUID | str, method: str = "cash", **extra
):
    """Settle as staff do: read the bill, then confirm the total shown for the method."""
    base = f"/api/restaurants/{slug}/bills/{bill_id}"
    detail = await client.get(base)
    preview = None
    if detail.status_code == 200:
        preview = next((m for m in detail.json()["methods"] if m["method"] == method), None)
    body = {
        "payment_method": method,
        "expected_method": method,
        "expected_total": preview["total"] if preview else "0",
        **extra,
    }
    return await client.post(f"{base}/settle", json=body)


async def open_table(
    db: AsyncSession, table_id: uuid.UUID, code: str | None = None
) -> TableSitting:
    """Staff seat a party: guests at the table may order (with `code` when one is required)."""
    sitting = TableSitting(table_id=table_id, code=code, code_required=code is not None)
    db.add(sitting)
    await db.flush()
    return sitting


@asynccontextmanager
async def _app_db() -> AsyncIterator[AsyncSession]:
    """The database session this test's requests use: the test's own, or a fresh one."""
    gen = app.dependency_overrides.get(get_db, get_db)()
    try:
        yield await anext(gen)
    finally:
        await gen.aclose()


async def seat_table(table_id: uuid.UUID) -> None:
    """Staff open the table (no code) unless it is open already, so its guests may order."""
    async with _app_db() as db:
        if await get_open_sitting(db, table_id) is None:
            await open_table(db, table_id)
        await db.commit()


async def approve_order(order_id: uuid.UUID | str) -> None:
    """The waiter approves the order's table if it is waiting, as POST .../approve does."""
    async with _app_db() as db:
        order = await db.get(Order, uuid.UUID(str(order_id)), populate_existing=True)
        if order.status == "pending_approval":
            await approve_pending(db, order.restaurant_id, order.table_id, "user:test")
        await db.commit()
