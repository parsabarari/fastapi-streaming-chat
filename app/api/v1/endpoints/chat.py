import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from app.config import Settings
from app.core.exceptions import LLMServiceError
from app.dependencies import get_redis_client, get_settings
from app.models.schemas import CacheStats, ChatRequest, HistoryResponse
from app.services import cache, context, llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Cached responses are replayed chunk-by-chunk with a tiny artificial delay
# so the frontend experience (progressive rendering) is identical whether a
# response came from the LLM or from cache.
_REPLAY_CHUNK_SIZE = 12
_REPLAY_DELAY_SECONDS = 0.015

# Bounded retry for errors that arrive mid-stream (HTTP 200, then an error
# embedded in the body once a backend is overloaded) - see stream_chat().
_MAX_STREAM_ATTEMPTS = 2
_STREAM_RETRY_DELAY_SECONDS = 1.0


def _chunk_text(text: str, size: int = _REPLAY_CHUNK_SIZE) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data)}


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    redis: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventSourceResponse:
    session_id = payload.session_id or str(uuid4())

    await context.append_message(
        redis, session_id, "user", payload.message, settings.max_context_messages, settings.session_ttl_seconds
    )
    history = await context.get_history(redis, session_id)
    cache_key = cache.make_cache_key(llm.SYSTEM_PROMPT, payload.message)

    async def event_generator():
        yield _sse("session", {"session_id": session_id})

        cached_response = await cache.get_cached_response(redis, cache_key)
        if cached_response is not None:
            await cache.record_hit(redis)
            for piece in _chunk_text(cached_response):
                yield _sse("chunk", {"content": piece})
                await asyncio.sleep(_REPLAY_DELAY_SECONDS)

            await context.append_message(
                redis,
                session_id,
                "assistant",
                cached_response,
                settings.max_context_messages,
                settings.session_ttl_seconds,
            )
            yield _sse("done", {"cached": True})
            return

        await cache.record_miss(redis)
        messages = [{"role": "system", "content": llm.SYSTEM_PROMPT}, *history]

        # OpenRouter (and some providers behind it) can return HTTP 200 and
        # then embed an error *inside* the stream body once a backend is
        # overloaded - this arrives as a normal exception while iterating,
        # not as a connection failure, so the tenacity retry in llm.py's
        # `_create_stream` never sees it. We add one bounded extra attempt
        # here, but only when zero chunks have reached the client yet -
        # once real content has been streamed, retrying would duplicate or
        # garble what the user already sees, so we give up instead.
        collected: list[str] = []
        stream_error: LLMServiceError | None = None
        for attempt in range(_MAX_STREAM_ATTEMPTS):
            collected = []
            try:
                async for delta in llm.stream_completion(messages):
                    collected.append(delta)
                    yield _sse("chunk", {"content": delta})
                stream_error = None
                break
            except LLMServiceError as exc:
                stream_error = exc
                if collected:
                    break
                is_last_attempt = attempt == _MAX_STREAM_ATTEMPTS - 1
                logger.warning(
                    "session=%s llm stream failed before any content (attempt %s/%s): %s",
                    session_id,
                    attempt + 1,
                    _MAX_STREAM_ATTEMPTS,
                    exc,
                )
                if not is_last_attempt:
                    await asyncio.sleep(_STREAM_RETRY_DELAY_SECONDS)

        if stream_error is not None:
            logger.error("session=%s llm streaming failed: %s", session_id, stream_error)
            yield _sse("error", {"message": str(stream_error)})
            return

        full_response = "".join(collected)
        if full_response:
            await cache.set_cached_response(redis, cache_key, full_response, settings.cache_ttl_seconds)
            await context.append_message(
                redis,
                session_id,
                "assistant",
                full_response,
                settings.max_context_messages,
                settings.session_ttl_seconds,
            )
        yield _sse("done", {"cached": False})

    return EventSourceResponse(event_generator())


@router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_chat_history(
    session_id: str,
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> HistoryResponse:
    messages = await context.get_history(redis, session_id)
    return HistoryResponse(session_id=session_id, messages=messages)


@router.get("/cache/metrics", response_model=CacheStats)
async def get_cache_metrics(
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> CacheStats:
    stats = await cache.get_cache_stats(redis)
    return CacheStats(**stats)