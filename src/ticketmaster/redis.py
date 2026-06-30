from __future__ import annotations

import redis.asyncio as redis

_redis_client: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize the async Redis client."""
    global _redis_client
    from ticketmaster.config import settings

    _redis_client = redis.from_url(settings.redis_url, decode_responses=False)


async def close_redis() -> None:
    """Close the Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> redis.Redis:
    """FastAPI dependency that yields the async Redis client."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis_client
