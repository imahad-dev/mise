"""Async Redis client and pub/sub helper."""

import json
import logging
import uuid

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


async def publish_declined(restaurant_id: uuid.UUID, order_ids: list[uuid.UUID]) -> None:
    """Waiting orders were cancelled: tell each guest's phone and the Floor (it reloads on
    kitchen events). Call AFTER db commit."""
    for order_id in order_ids:
        declined = json.dumps({"event": "order_declined", "order_id": str(order_id)})
        await publish_event(f"kitchen:{restaurant_id}", declined)
        await publish_event(f"orders:{order_id}", declined)


async def check_redis() -> bool:
    """Ping Redis, return True if healthy."""
    try:
        return await redis_client.ping()
    except Exception:
        return False
