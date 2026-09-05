import json

from redis.asyncio import Redis

SESSION_KEY_PREFIX = "session:"


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


async def get_history(redis: Redis, session_id: str) -> list[dict]:
    """Return the stored message history for a session (empty if unseen)."""
    raw = await redis.get(_session_key(session_id))
    if raw is None:
        return []
    return json.loads(raw)


async def append_message(
    redis: Redis,
    session_id: str,
    role: str,
    content: str,
    max_messages: int,
    ttl_seconds: int,
) -> list[dict]:
    """Append a message to a session's history, applying the sliding window
    (Decision 7) *before* persisting, then refresh the TTL so active
    sessions don't expire mid-conversation.

    Each session is stored under its own key (`session:{id}`), which is
    what gives us real session isolation rather than a single shared list.
    """
    history = await get_history(redis, session_id)
    history.append({"role": role, "content": content})

    if max_messages > 0 and len(history) > max_messages:
        history = history[-max_messages:]

    await redis.set(_session_key(session_id), json.dumps(history), ex=ttl_seconds)
    return history
