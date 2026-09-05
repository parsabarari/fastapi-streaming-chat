import logging
from collections.abc import AsyncGenerator

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.exceptions import LLMServiceError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are a helpful, concise assistant."

# Transient errors worth retrying with backoff.
RETRYABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError)
# Errors that will never succeed on retry (bad key, malformed request,
# insufficient permissions/credits - the latter matters on OpenRouter,
# which returns 402/403 when a key is out of credit).
NON_RETRYABLE_ERRORS = (AuthenticationError, BadRequestError, NotFoundError, PermissionDeniedError)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Lazily-created singleton client.

    Works against real OpenAI by default. If `settings.openai_base_url` is
    set (e.g. to OpenRouter's endpoint), requests are routed there instead
    with the same client - OpenRouter speaks the OpenAI API shape, so no
    SDK or code changes are needed, only config.
    """
    global _client
    if _client is None:
        extra_headers = {}
        if settings.app_referrer_url:
            extra_headers["HTTP-Referer"] = settings.app_referrer_url
        if settings.app_title:
            extra_headers["X-Title"] = settings.app_title

        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_headers=extra_headers or None,
        )
    return _client


@retry(
    retry=retry_if_exception_type(RETRYABLE_ERRORS),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _create_stream(client: AsyncOpenAI, messages: list[dict], model: str):
    """Open the streaming completion. Retried (with exponential backoff) on
    transient errors only - retrying is applied here, to the connection
    attempt, rather than around the whole generator below, since chunks
    already yielded to the client can't be "un-sent".
    """
    return await client.chat.completions.create(model=model, messages=messages, stream=True)


async def stream_completion(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Stream completion text deltas for a chat request.

    Raises LLMServiceError (never leaks raw OpenAI exceptions) on:
      - a non-retryable error (bad API key, malformed request, ...)
      - a retryable error that still failed after all retry attempts
      - a failure that happens mid-stream, once tokens have started arriving
    """
    client = get_openai_client()

    try:
        stream = await _create_stream(client, messages, settings.openai_model)
    except NON_RETRYABLE_ERRORS as exc:
        logger.error("Non-retryable LLM error: %s", exc)
        raise LLMServiceError(f"LLM request was rejected: {exc}") from exc
    except RETRYABLE_ERRORS as exc:
        logger.error("LLM error persisted after retries: %s", exc)
        raise LLMServiceError("LLM service is temporarily unavailable, please try again.") from exc

    try:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as exc:  # noqa: BLE001 - surface any mid-stream failure uniformly
        logger.error("LLM streaming was interrupted: %s", exc)
        raise LLMServiceError("LLM stream was interrupted.") from exc
    