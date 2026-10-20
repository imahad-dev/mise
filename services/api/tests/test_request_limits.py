"""Client IP resolution behind trusted proxies, and the per-IP limit helper."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.config import settings
from src.request_limits import client_ip, enforce_ip_limit


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


@pytest.fixture(autouse=True)
def _docker_cidr():
    with patch.object(settings, "trusted_proxy_cidrs", ["172.16.0.0/12"]):
        yield


def test_untrusted_peer_ignores_forwarded_header():
    assert client_ip(_request("203.0.113.9", "198.51.100.1")) == "203.0.113.9"


def test_trusted_peer_uses_forwarded_client():
    assert client_ip(_request("172.18.0.5", "198.51.100.1")) == "198.51.100.1"


def test_trusted_peer_takes_rightmost_untrusted_hop():
    # The client prepended a fake hop; the proxy chain appended the real one.
    assert client_ip(_request("172.18.0.5", "1.1.1.1, 198.51.100.1, 172.18.0.7")) == (
        "198.51.100.1"
    )


def test_trusted_peer_without_header_or_with_garbage_uses_peer():
    assert client_ip(_request("172.18.0.5")) == "172.18.0.5"
    assert client_ip(_request("172.18.0.5", "not-an-ip, ")) == "172.18.0.5"


def test_distinct_visitors_behind_proxy_get_distinct_buckets():
    a = client_ip(_request("172.18.0.5", "198.51.100.1"))
    b = client_ip(_request("172.18.0.5", "198.51.100.2"))
    assert a != b


@pytest.mark.asyncio
async def test_enforce_ip_limit_429_after_limit():
    with (
        patch("src.request_limits.redis_client.incr", new_callable=AsyncMock) as incr,
        patch("src.request_limits.redis_client.expire", new_callable=AsyncMock) as expire,
    ):
        incr.return_value = 1
        await enforce_ip_limit(_request("203.0.113.9"), "t", limit=3, window_s=60, detail="x")
        incr.assert_awaited_with("rate_limit:t:203.0.113.9")
        expire.assert_awaited_with("rate_limit:t:203.0.113.9", 60)

        incr.return_value = 4
        with pytest.raises(HTTPException) as exc:
            await enforce_ip_limit(_request("203.0.113.9"), "t", limit=3, window_s=60, detail="x")
        assert exc.value.status_code == 429
