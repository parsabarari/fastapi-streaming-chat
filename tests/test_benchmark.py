"""Benchmarks the cache's impact on response latency.

This is intentionally a reporting script dressed as a test (per the
roadmap): run it with `pytest -s tests/test_benchmark.py` to see the
printed numbers. The only hard assertion is the direction of the effect
(cached must be faster) - the roadmap asks for a report, not a strict SLA.
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from app.services import llm

pytestmark = pytest.mark.asyncio

# Simulated upstream latency, standing in for a real OpenAI network round trip.
_SIMULATED_LLM_LATENCY_SECONDS = 0.05


async def _slow_stream(messages):
    await asyncio.sleep(_SIMULATED_LLM_LATENCY_SECONDS)
    for token in ["This ", "is ", "a ", "simulated ", "LLM ", "response."]:
        yield token


async def test_cache_speeds_up_repeated_requests(client):
    payload = {"session_id": "bench-session", "message": "What is the speed of light?"}

    with patch.object(llm, "stream_completion", _slow_stream):
        start = time.perf_counter()
        await client.post("/api/v1/chat/stream", json=payload)
        uncached_duration = time.perf_counter() - start

        start = time.perf_counter()
        await client.post("/api/v1/chat/stream", json=payload)
        cached_duration = time.perf_counter() - start

    print(f"\nUncached request : {uncached_duration * 1000:.1f} ms")
    print(f"Cached request   : {cached_duration * 1000:.1f} ms")
    print(f"Speedup          : {uncached_duration / cached_duration:.2f}x")

    assert cached_duration < uncached_duration
