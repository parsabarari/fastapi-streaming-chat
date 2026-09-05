import pytest

from app.services import context

pytestmark = pytest.mark.asyncio


async def test_context_limit(fake_redis):
    session_id = "session-a"
    for i in range(15):
        await context.append_message(
            fake_redis, session_id, "user", f"message {i}", max_messages=10, ttl_seconds=60
        )

    history = await context.get_history(fake_redis, session_id)

    assert len(history) == 10
    # Only the most recent 10 of 15 messages should survive the window.
    assert history[0]["content"] == "message 5"
    assert history[-1]["content"] == "message 14"


async def test_session_isolation(fake_redis):
    await context.append_message(fake_redis, "session-a", "user", "hello from a", max_messages=10, ttl_seconds=60)
    await context.append_message(fake_redis, "session-b", "user", "hello from b", max_messages=10, ttl_seconds=60)

    history_a = await context.get_history(fake_redis, "session-a")
    history_b = await context.get_history(fake_redis, "session-b")

    assert len(history_a) == 1
    assert len(history_b) == 1
    assert history_a[0]["content"] == "hello from a"
    assert history_b[0]["content"] == "hello from b"


async def test_unknown_session_returns_empty_history(fake_redis):
    history = await context.get_history(fake_redis, "never-seen-session")
    assert history == []
