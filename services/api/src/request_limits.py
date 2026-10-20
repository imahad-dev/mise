"""Client IP resolution behind trusted proxies, and Redis fixed-window limits per client IP."""

import ipaddress
import logging

from fastapi import HTTPException, Request, status

from src.config import settings
from src.redis_client import redis_client

logger = logging.getLogger(__name__)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(ip in ipaddress.ip_network(c, strict=False) for c in settings.trusted_proxy_cidrs)


def client_ip(request: Request) -> str:
    """The client address used for rate limits.

    When the immediate peer is a trusted proxy (TRUSTED_PROXY_CIDRS), walk X-Forwarded-For
    from the right and return the first hop that is not itself a trusted proxy. Hops further
    left were written by the client and could be spoofed. Otherwise use the peer address.
    """
    peer = request.client.host if request.client else "127.0.0.1"
    peer_ip = _parse_ip(peer)
    if peer_ip is None or not _is_trusted(peer_ip):
        return peer
    hops = [_parse_ip(h) for h in request.headers.get("x-forwarded-for", "").split(",")]
    hops = [h for h in hops if h is not None]
    for hop in reversed(hops):
        if not _is_trusted(hop):
            return str(hop)
    return str(hops[0]) if hops else peer


async def enforce_ip_limit(
    request: Request, scope: str, limit: int, window_s: int, detail: str
) -> None:
    """Allow `limit` requests per `window_s` seconds per client IP; 429 beyond that.

    Redis errors are logged and the request is allowed (fail open), like the other limits.
    """
    key = f"rate_limit:{scope}:{client_ip(request)}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_s)
        if count > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Redis error checking %s rate limit: %s", scope, e)
