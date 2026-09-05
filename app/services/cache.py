import hashlib

from redis.asyncio import Redis

CACHE_KEY_PREFIX = "cache:"
HITS_KEY = "metrics:cache_hits"
MISSES_KEY = "metrics:cache_misses"


def make_cache_key(system_prompt: str, user_message: str) -> str:
    """Exact-match cache key: sha256(system_prompt + "|" + user_message).

    Deliberately does NOT include the conversation context/history (Decision
    5) - if it did, near-identical requests would (almost) never share a
    key and we'd never get a cache hit. Semantic caching (embedding
    similarity) is out of scope for this project; it belongs to Week 6.
    """
    digest = hashlib.sha256(f"{system_prompt}|{user_message}".encode("utf-8")).hexdigest()
    return f"{CACHE_KEY_PREFIX}{digest}"


async def get_cached_response(redis: Redis, key: str) -> str | None:
    return await redis.get(key)


async def set_cached_response(redis: Redis, key: str, response: str, ttl_seconds: int) -> None:
    await redis.set(key, response, ex=ttl_seconds)


async def record_hit(redis: Redis) -> None:
    await redis.incr(HITS_KEY)


async def record_miss(redis: Redis) -> None:
    await redis.incr(MISSES_KEY)


async def get_cache_stats(redis: Redis) -> dict:
    hits_raw, misses_raw = await redis.mget(HITS_KEY, MISSES_KEY)
    hits = int(hits_raw or 0)
    misses = int(misses_raw or 0)
    total = hits + misses
    hit_rate = hits / total if total else 0.0
    return {"hits": hits, "misses": misses, "hit_rate": hit_rate}
