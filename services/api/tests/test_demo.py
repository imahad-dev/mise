"""Tests for demo mode endpoints: /api/auth/config, /api/auth/demo-login, /api/demo/info."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from scripts.seed import load_seed_data, seed_data
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member, make_user

from src.config import settings
from src.models.menu import MenuItem
from src.models.restaurant import Restaurant


async def _demo_venue(db: AsyncSession) -> Restaurant:
    venue = Restaurant(
        name="Demo venue",
        slug=settings.demo_restaurant_slugs[0],
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db.add(venue)
    await db.flush()
    return venue


@pytest.mark.asyncio
async def test_auth_config_endpoint(client: AsyncClient):
    """GET /api/auth/config returns the configured demo_mode flag."""
    resp = await client.get("/api/auth/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "demo_mode" in data
    assert data["demo_mode"] == settings.demo_mode


@pytest.mark.asyncio
async def test_demo_login_404_when_demo_mode_false(client: AsyncClient):
    """POST /api/auth/demo-login returns 404 when DEMO_MODE is false."""
    with patch.object(settings, "demo_mode", False):
        resp = await client.post(
            "/api/auth/demo-login",
            json={"role": "owner"},
        )
        assert resp.status_code == 404
        assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_demo_login_sets_cookie_when_demo_mode_true(
    client: AsyncClient, db_session: AsyncSession
):
    """POST /api/auth/demo-login signs in the seeded demo owner when DEMO_MODE is true."""
    venue = await _demo_venue(db_session)
    await make_user(db_session, [(venue.id, "owner")], email=settings.demo_owner_email)
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock) as mock_incr,
        patch("src.routers.auth.redis_client.expire", new_callable=AsyncMock) as mock_expire,
    ):
        mock_incr.return_value = 1
        resp = await client.post(
            "/api/auth/demo-login",
            json={"role": "owner"},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "name": "Test user",
            "email": settings.demo_owner_email,
        }
        assert "mise_auth" in resp.cookies
        assert mock_incr.called
        assert mock_expire.called


@pytest.mark.asyncio
async def test_demo_login_staff_uses_venue_staff_user(
    client: AsyncClient, db_session: AsyncSession
):
    """Staff demo login signs in demo-staff+<venue>@mise.demo, defaulting to the first venue."""
    venue = await _demo_venue(db_session)
    email = f"demo-staff+{venue.slug}@mise.demo"
    await make_user(db_session, [(venue.id, "staff")], email=email)
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock, return_value=1),
        patch("src.routers.auth.redis_client.expire", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/auth/demo-login", json={"role": "staff"})
        assert resp.status_code == 200
        assert resp.json()["email"] == email
        me = await client.get("/api/auth/me")
        assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_demo_login_rejects_venue_outside_demo_list(
    client: AsyncClient, db_session: AsyncSession
):
    """A staff user named like a demo user is not reachable unless its venue is a demo venue."""
    venue = Restaurant(
        name="Private",
        slug="private-venue",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(venue)
    await db_session.flush()
    await make_user(db_session, [(venue.id, "staff")], email="demo-staff+private-venue@mise.demo")
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock, return_value=1),
        patch("src.routers.auth.redis_client.expire", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/auth/demo-login", json={"role": "staff", "venue": "private-venue"}
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Demo user not found"
    assert "mise_auth" not in resp.cookies


@pytest.mark.asyncio
async def test_demo_login_404_when_demo_user_not_seeded(client: AsyncClient):
    """Without the seeded demo users, demo login is a 404, not a session for nobody."""
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock, return_value=1),
        patch("src.routers.auth.redis_client.expire", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/auth/demo-login", json={"role": "staff"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Demo user not found"


@pytest.mark.asyncio
async def test_demo_login_rate_limit_429(client: AsyncClient):
    """POST /api/auth/demo-login returns 429 when rate limit of 20/min is exceeded."""
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock) as mock_incr,
    ):
        mock_incr.return_value = 21  # 21st attempt exceeds limit of 20
        resp = await client.post(
            "/api/auth/demo-login",
            json={"role": "owner"},
        )
        assert resp.status_code == 429
        assert "rate limit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_demo_info_404_when_demo_mode_false(client: AsyncClient):
    """GET /api/demo/info returns 404 when DEMO_MODE is false."""
    with patch.object(settings, "demo_mode", False):
        resp = await client.get("/api/demo/info")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_demo_info_200_when_demo_mode_true(client: AsyncClient):
    """GET /api/demo/info returns guest, owner, and kitchen URLs when DEMO_MODE is true."""
    with patch.object(settings, "demo_mode", True):
        resp = await client.get("/api/demo/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "guest_url" in data
        assert "owner_url" in data
        assert "kitchen_url" in data
        assert data["kitchen_url"].endswith("/kitchen")


async def _menu_count(db: AsyncSession, restaurant_id) -> int:
    stmt = select(func.count()).select_from(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
    return (await db.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_demo_reset_reseeds_only_its_own_venue(client: AsyncClient, db_session: AsyncSession):
    """Reset loads the seed whose slug is this venue's; other venues are untouched."""
    await seed_data(load_seed_data("data/seed/trattoria_da_mario.json"), db_session)
    mine = (
        await db_session.execute(select(Restaurant).where(Restaurant.slug == "trattoria-da-mario"))
    ).scalar_one()
    other = Restaurant(
        name="Other venue",
        slug="other-venue",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        MenuItem(
            restaurant_id=other.id,
            category="mains",
            price=Decimal("500.00"),
            unit_cost=Decimal("200.00"),
        )
    )
    mine.name = "Renamed by owner"
    await db_session.flush()
    other_items = await _menu_count(db_session, other.id)

    await as_member(client, db_session, mine.id, "owner")
    with patch.object(settings, "demo_mode", True):
        resp = await client.post("/api/restaurants/trattoria-da-mario/demo/reset")
    assert resp.status_code == 200, resp.text

    await db_session.refresh(mine)
    await db_session.refresh(other)
    assert mine.name == "Trattoria da Mario"
    assert (other.name, other.slug) == ("Other venue", "other-venue")
    assert await _menu_count(db_session, other.id) == other_items


@pytest.mark.asyncio
async def test_demo_reset_404_without_a_seed_for_the_venue(
    client: AsyncClient, db_session: AsyncSession
):
    """An owner of a venue with no seed file cannot trigger any re-seed."""
    venue = Restaurant(
        name="No seed",
        slug="no-seed-venue",
        currency="PKR",
        timezone="Asia/Karachi",
        languages=["en"],
        default_language="en",
    )
    db_session.add(venue)
    await db_session.flush()
    await as_member(client, db_session, venue.id, "owner")
    with patch.object(settings, "demo_mode", True):
        resp = await client.post("/api/restaurants/no-seed-venue/demo/reset")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No demo seed for this restaurant"
