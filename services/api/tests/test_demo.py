"""Tests for demo mode endpoints: /api/auth/config, /api/auth/demo-login, /api/demo/info."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.config import settings


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
async def test_demo_login_sets_cookie_when_demo_mode_true(client: AsyncClient):
    """POST /api/auth/demo-login sets signed mise_auth cookie when DEMO_MODE is true."""
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
        assert resp.json() == {"status": "ok", "role": "owner"}
        assert "mise_auth" in resp.cookies
        assert mock_incr.called
        assert mock_expire.called


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
