"""Async Redis client and pub/sub helper."""

import logging

import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)

redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def publish_event(channel: str, message: str) -> None:
    """Publish a message to a Redis channel. Call AFTER db commit.

    A publish failure is logged and never fails the caller.
    """
    try:
        await redis_client.publish(channel, message)
    except Exception as e:
        logger.error("Failed to publish to redis channel %s: %s", channel, e)


async def check_redis() -> bool:
    """Ping Redis, return True if healthy."""
    try:
        return await redis_client.ping()
    except Exception:
        return False
