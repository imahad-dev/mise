"""Async Redis client and pub/sub helper."""

import redis.asyncio as aioredis

from src.config import settings

redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def publish_event(channel: str, message: str) -> None:
    """Publish a message to a Redis channel. Call AFTER db commit."""
    await redis_client.publish(channel, message)


async def check_redis() -> bool:
    """Ping Redis, return True if healthy."""
    try:
        return await redis_client.ping()
    except Exception:
        return False
