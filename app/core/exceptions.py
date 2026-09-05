from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class LLMServiceError(Exception):
    """Raised when the upstream LLM provider fails (after retries were
    exhausted) or returns a non-retryable error (bad key, bad request, ...).
    """


class CacheError(Exception):
    """Raised when the Redis-backed cache/session store is unavailable or
    misbehaves.
    """


def register_exception_handlers(app: FastAPI) -> None:
    """Wire up global exception -> HTTP response translation.

    LLMServiceError -> 503 (upstream dependency unavailable)
    CacheError       -> 500 (our own infra failed)
    """

    @app.exception_handler(LLMServiceError)
    async def _llm_service_error_handler(request: Request, exc: LLMServiceError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(CacheError)
    async def _cache_error_handler(request: Request, exc: CacheError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
