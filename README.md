# fastapi-streaming-chat

A production-style FastAPI chat backend: SSE streaming from OpenAI, a
Redis-backed exact-match response cache with hit/miss metrics, per-session
conversation history with a sliding window, and retry/backoff on transient
upstream failures. Built as one integrated project (not three separate
exercises) — see `fastapi-streaming-chat-roadmap.md` for the full design
log and decision rationale.

## Architecture

```
Frontend (fetch + ReadableStream)
        │  POST /api/v1/chat/stream
        ▼
FastAPI endpoint (app/api/v1/endpoints/chat.py)
        │
        ├─▶ services/context.py  ── sliding-window history, per-session key in Redis
        ├─▶ services/cache.py    ── exact-match cache (sha256 of system+message), hit/miss counters
        └─▶ services/llm.py      ── AsyncOpenAI streaming, tenacity retry/backoff on transient errors
                │
                ▼
        OpenAI Chat Completions API (streamed)
```

Every request: append the user message to the session's history in Redis →
check the cache for that exact message → on a hit, replay the cached text
as fake "chunks" over SSE (same UX, zero API cost); on a miss, stream from
OpenAI with retries, cache the finished response, and append it to history.

### Why the cache ignores conversation context

The cache key is `sha256(system_prompt + "|" + user_message)` — it does
**not** include the rest of the conversation. If it did, virtually every
request would have a unique key (since the history preceding it differs
almost every time) and the cache would never hit. This is a deliberate
scope decision for this stage of the project: the cache proves that an
*exact repeat* of a question doesn't hit the LLM API again. Semantic
caching (embedding similarity, so paraphrased questions can also hit) is
explicitly deferred to the Week 6 embeddings project.

## Running locally (uv)

```bash
cp .env.example .env        # then fill in OPENAI_API_KEY
uv sync
redis-server &               # or run Redis any other way
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000 for the test frontend, or use curl:

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What is FastAPI?"}'
```

```bash
curl http://localhost:8000/api/v1/chat/<session_id>/history
curl http://localhost:8000/api/v1/chat/cache/metrics
```

## Running with Docker

```bash
docker compose up --build
```

This starts the app (`:8000`) and a real Redis container together.

## Running tests

Tests never call the real OpenAI API and never require a real Redis — they
use `fakeredis` for storage and mock `services.llm.stream_completion`
directly.

```bash
uv sync --group dev
uv run pytest
```

To see the cache benchmark numbers:

```bash
uv run pytest -s tests/test_benchmark.py
```

## API contract

```
POST /api/v1/chat/stream
Content-Type: application/json
Body: { "session_id": "optional-string", "message": "string" }
Response: text/event-stream
  event: session   data: {"session_id": "..."}
  event: chunk     data: {"content": "..."}
  event: error     data: {"message": "..."}      (only on failure)
  event: done      data: {"cached": true|false}

GET /api/v1/chat/{session_id}/history
Response: 200 { "session_id": "...", "messages": [{"role": "...", "content": "..."}] }

GET /api/v1/chat/cache/metrics
Response: 200 { "hits": 0, "misses": 0, "hit_rate": 0.0 }

GET /health
Response: 200 { "status": "ok" }
```

## Notes for whoever picks this up next

- The full decision log (why SSE over WebSocket, why Redis for both cache
  and sessions, why sliding window over summarization, etc.) lives in
  `fastapi-streaming-chat-roadmap.md`. Read it before changing architecture.
- `uv.lock` was not regenerated in this pass (no network access when these
  files were written) — run `uv lock` once you have connectivity so
  `sse-starlette`, `tenacity`, and `fakeredis` are pinned.
