from unittest.mock import patch

import pytest

from app.core.exceptions import LLMServiceError
from app.services import llm

pytestmark = pytest.mark.asyncio


async def _fake_stream(messages):
    for token in ["Hello", ", ", "world", "!"]:
        yield token


async def _failing_stream(messages):
    raise LLMServiceError("upstream is down")
    yield  # pragma: no cover - keeps this an async generator


async def _collect_sse(response):
    body = ""
    async for line in response.aiter_lines():
        body += line + "\n"
    return body


async def test_stream_response(client):
    with patch.object(llm, "stream_completion", _fake_stream):
        async with client.stream("POST", "/api/v1/chat/stream", json={"message": "Hi there"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = await _collect_sse(response)

    assert "event: session" in body
    assert "event: chunk" in body
    assert "event: done" in body
    assert "Hello" in body
    assert '"cached": false' in body


async def test_cached_response_is_replayed_and_flagged(client):
    payload = {"session_id": "cache-session", "message": "What is the speed of light?"}

    with patch.object(llm, "stream_completion", _fake_stream):
        async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
            await _collect_sse(response)

        # Second identical message should be served from cache without
        # touching stream_completion again.
        with patch.object(llm, "stream_completion", side_effect=AssertionError("LLM should not be called on a cache hit")):
            async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
                body = await _collect_sse(response)

    assert '"cached": true' in body


async def test_history_round_trip(client):
    payload = {"session_id": "hist-session", "message": "Hi"}
    with patch.object(llm, "stream_completion", _fake_stream):
        async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
            await _collect_sse(response)

    history_resp = await client.get("/api/v1/chat/hist-session/history")

    assert history_resp.status_code == 200
    data = history_resp.json()
    assert data["session_id"] == "hist-session"
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]


async def test_error_handling(client):
    with patch.object(llm, "stream_completion", _failing_stream):
        async with client.stream("POST", "/api/v1/chat/stream", json={"message": "Hi"}) as response:
            body = await _collect_sse(response)

    assert "event: error" in body
    assert "upstream is down" in body
