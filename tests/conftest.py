import os

# Must be set before `app.config` / `app.main` are imported anywhere, since
# Settings() is instantiated at import time and requires OPENAI_API_KEY.
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-a-real-secret")
os.environ.setdefault("ENVIRONMENT", "test")

import fakeredis.aioredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_redis_client
from app.main import app


@pytest_asyncio.fixture
async def fake_redis():
    """A fresh in-memory fake Redis per test - avoids requiring a real
    Redis instance for unit tests and keeps tests isolated from each other.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(fake_redis):
    """An httpx AsyncClient wired directly to the ASGI app, with the Redis
    dependency overridden to use the fake client above (so the real
    lifespan-managed Redis connection is never touched in tests).
    """
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
