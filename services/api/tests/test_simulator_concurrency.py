"""Concurrent 'Generate demo data' requests must not double the simulated orders.

Uses committed data through the real session factory (no per-test rollback), so two requests
run in separate transactions exactly as in production. Teardown deletes everything created.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from src.auth import AUTH_COOKIE_NAME, sign_value
from src.config import settings
from src.database import async_session_factory, get_db
from src.main import app
from src.models.audit import AuditLog
from src.models.forecast import ForecastRun
from src.models.menu import MenuItem, MenuTranslation
from src.models.order import Order, OrderItem
from src.models.restaurant import Restaurant
from src.models.session import GuestSession
from src.redis_client import redis_client
from src.services.simulator import SimAssumptions, generate_orders

RATE_KEY = "rate_limit:demo:simulate:127.0.0.1"
DAYS = 14


@pytest_asyncio.fixture
async def committed_restaurant():
    restaurant_id = uuid.uuid4()
    slug = f"sim-concurrency-{uuid.uuid4().hex[:8]}"
    async with async_session_factory() as s:
        s.add(
            Restaurant(
                id=restaurant_id,
                name="Concurrency Trattoria",
                slug=slug,
                timezone="Europe/Rome",
                languages=["en", "it"],
                default_language="en",
                currency="EUR",
            )
        )
        await s.flush()
        for n in range(6):
            item_id = uuid.uuid4()
            s.add(
                MenuItem(
                    id=item_id,
                    restaurant_id=restaurant_id,
                    category="mains",
                    price=Decimal("10.00") + n,
                    unit_cost=Decimal("3.00"),
                    allergen_verified=True,
                )
            )
            await s.flush()
            s.add(MenuTranslation(menu_item_id=item_id, language="en", name=f"Dish {n}"))
        await s.commit()
    await redis_client.delete(RATE_KEY)
    try:
        yield restaurant_id, slug
    finally:
        await redis_client.delete(RATE_KEY)
        async with async_session_factory() as s:
            await s.execute(delete(AuditLog).where(AuditLog.restaurant_id == restaurant_id))
            await s.execute(delete(ForecastRun).where(ForecastRun.restaurant_id == restaurant_id))
            await s.execute(delete(Order).where(Order.restaurant_id == restaurant_id))
            await s.execute(delete(GuestSession).where(GuestSession.restaurant_id == restaurant_id))
            item_ids = select(MenuItem.id).where(MenuItem.restaurant_id == restaurant_id)
            await s.execute(
                delete(MenuTranslation).where(MenuTranslation.menu_item_id.in_(item_ids))
            )
            await s.execute(delete(MenuItem).where(MenuItem.restaurant_id == restaurant_id))
            await s.execute(delete(Restaurant).where(Restaurant.id == restaurant_id))
            await s.commit()


async def _counts(restaurant_id: uuid.UUID) -> tuple[int, int, int]:
    async with async_session_factory() as s:
        orders = (
            await s.execute(
                select(func.count()).select_from(Order).where(Order.restaurant_id == restaurant_id)
            )
        ).scalar_one()
        items = (
            await s.execute(
                select(func.count())
                .select_from(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(Order.restaurant_id == restaurant_id)
            )
        ).scalar_one()
        sessions = (
            await s.execute(
                select(func.count())
                .select_from(GuestSession)
                .where(GuestSession.restaurant_id == restaurant_id)
            )
        ).scalar_one()
    return orders, items, sessions


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_concurrent_generate_demo_data_equals_one_run(committed_restaurant):
    restaurant_id, slug = committed_restaurant
    saved_override = app.dependency_overrides.pop(get_db, None)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            ac.cookies.set(AUTH_COOKIE_NAME, sign_value(f"owner:{int(time.time()) + 3600}"))
            url = f"/api/restaurants/{slug}/demo/simulate-orders"
            with patch.object(settings, "demo_mode", True):
                r1, r2 = await asyncio.gather(
                    ac.post(url, json={"days": DAYS}), ac.post(url, json={"days": DAYS})
                )
    finally:
        if saved_override is not None:
            app.dependency_overrides[get_db] = saved_override

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text

    # Expected counts of a single run, from the same pure generator the endpoint uses
    async with async_session_factory() as s:
        ids = list(
            (await s.execute(select(MenuItem.id).where(MenuItem.restaurant_id == restaurant_id)))
            .scalars()
            .all()
        )
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    expected = generate_orders(
        ids, today - timedelta(days=DAYS), SimAssumptions(days=DAYS), ZoneInfo("Europe/Rome")
    )
    expected_orders = len(expected)
    expected_items = sum(len(o.lines) for o in expected)

    assert r1.json()["orders_created"] == r2.json()["orders_created"] == expected_orders
    assert await _counts(restaurant_id) == (expected_orders, expected_items, 1)


@pytest.mark.asyncio
async def test_simulate_orders_rate_limited_per_ip(committed_restaurant):
    _, slug = committed_restaurant
    await redis_client.set(RATE_KEY, 3)  # three generations already used this hour
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.cookies.set(AUTH_COOKIE_NAME, sign_value(f"owner:{int(time.time()) + 3600}"))
        with patch.object(settings, "demo_mode", True):
            resp = await ac.post(f"/api/restaurants/{slug}/demo/simulate-orders", json={})
    assert resp.status_code == 429
