from functools import lru_cache

from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings, settings


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached for cheap DI)."""
    return settings


def get_redis_client(request: Request) -> Redis:
    """Return the shared async Redis client created in the app lifespan.

    Using request.app.state means we open a single connection pool at
    startup instead of a new connection per-request.
    """
    return request.app.state.redis
