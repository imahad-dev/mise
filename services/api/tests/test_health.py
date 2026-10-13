"""Tests for health and debug SSE endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_debug_sse_streams(client: AsyncClient):
    """Debug SSE endpoint returns event-stream content type."""
    async with client.stream("GET", "/debug/sse") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Read initial event (heartbeat is 15s)
        count = 0
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                count += 1
                if count >= 1:
                    break
        assert count >= 1
