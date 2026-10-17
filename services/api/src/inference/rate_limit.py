"""Redis-backed rate limiting for inference calls.

Two limiters:
- Global RPM: sliding-window counter keyed by minute
- Per-guest session: simple counter with session-lifetime TTL
"""

from __future__ import annotations

import time

from fastapi import HTTPException, status

from src.config import settings
from src.redis_client import redis_client


async def check_global_rate_limit() -> None:
    """Enforce global requests-per-minute limit via Redis INCR + EXPIRE.

    Raises 429 if the configured RPM ceiling is exceeded.
    """
    if settings.llm_global_rpm <= 0:
        return  # unlimited

    window_key = f"mise:llm:rpm:{int(time.time()) // 60}"
    count = await redis_client.incr(window_key)
    if count == 1:
        await redis_client.expire(window_key, 120)  # 2-min TTL for clock skew safety

    if count > settings.llm_global_rpm:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Global inference rate limit exceeded. Please retry shortly.",
        )


async def check_guest_chat_limit(session_id: str) -> None:
    """Enforce per-guest-session message cap.

    Raises 429 if the guest has exhausted their chat allowance.
    """
    if settings.guest_chat_limit <= 0:
        return  # unlimited

    counter_key = f"mise:chat:session:{session_id}"
    count = await redis_client.incr(counter_key)
    if count == 1:
        # 4-hour TTL matches session lifetime
        await redis_client.expire(counter_key, 4 * 3600)

    if count > settings.guest_chat_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Chat message limit reached for this session.",
        )
