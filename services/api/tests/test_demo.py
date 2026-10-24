"""Tests for demo mode endpoints: /api/auth/config, /api/auth/demo-login, /api/demo/info."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import make_user

from src.config import settings
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
async def test_demo_login_404_when_demo_user_not_seeded(client: AsyncClient):
    """Without the seeded demo users, demo login is a 404, not a session for nobody."""
    with (
        patch.object(settings, "demo_mode", True),
        patch("src.routers.auth.redis_client.incr", new_callable=AsyncMock, return_value=1),
        patch("src.routers.auth.redis_client.expire", new_callable=AsyncMock),
    ):
        resp = await client.post("/api/auth/demo-login", json={"role": "staff", "venue": "none"})
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
