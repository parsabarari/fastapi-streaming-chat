import pytest

from app.services import cache

pytestmark = pytest.mark.asyncio


async def test_cache_miss(fake_redis):
    key = cache.make_cache_key("system prompt", "a question nobody asked yet")
    result = await cache.get_cached_response(fake_redis, key)
    assert result is None


async def test_cache_hit(fake_redis):
    key = cache.make_cache_key("system prompt", "what is fastapi?")
    await cache.set_cached_response(fake_redis, key, "FastAPI is a modern Python web framework.", ttl_seconds=60)

    result = await cache.get_cached_response(fake_redis, key)

    assert result == "FastAPI is a modern Python web framework."


async def test_cache_key_ignores_context_only_system_and_message(fake_redis):
    # Decision 5: the cache key is a function of (system_prompt, message)
    # only - it must be stable regardless of any surrounding conversation.
    key1 = cache.make_cache_key("system", "same question")
    key2 = cache.make_cache_key("system", "same question")
    key3 = cache.make_cache_key("system", "different question")

    assert key1 == key2
    assert key1 != key3


async def test_cache_stats_hit_rate(fake_redis):
    await cache.record_hit(fake_redis)
    await cache.record_hit(fake_redis)
    await cache.record_miss(fake_redis)

    stats = await cache.get_cache_stats(fake_redis)

    assert stats == {"hits": 2, "misses": 1, "hit_rate": pytest.approx(2 / 3)}


async def test_cache_stats_defaults_to_zero(fake_redis):
    stats = await cache.get_cache_stats(fake_redis)
    assert stats == {"hits": 0, "misses": 0, "hit_rate": 0.0}
