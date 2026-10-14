"""Tests for health and debug SSE endpoints."""

import asyncio
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.routers.health import _debug_sse_generator


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_debug_sse_generator_direct():
    """Test the generator directly: anext once, then aclose, confirming CancelledError."""
    gen = _debug_sse_generator()
    first = await anext(gen)
    assert first == 'data: {"count": 0, "msg": "debug heartbeat"}\n\n'

    # Confirm cancelling/closing re-raises CancelledError
    with pytest.raises(asyncio.CancelledError):
        await gen.athrow(asyncio.CancelledError)
    await gen.aclose()


@pytest.mark.asyncio
async def test_debug_sse_endpoint_headers(client: AsyncClient):
    """Test the route headers using a patched generator that yields once and ends."""

    async def _mock_sse_generator():
        yield 'data: {"count": 0, "msg": "debug heartbeat"}\n\n'

    with patch("src.routers.health._debug_sse_generator", _mock_sse_generator):
        resp = await client.get("/debug/sse")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("connection") == "keep-alive"
        assert resp.headers.get("x-accel-buffering") == "no"
        assert 'data: {"count": 0, "msg": "debug heartbeat"}' in resp.text
