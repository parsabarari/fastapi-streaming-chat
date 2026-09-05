from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One Redis connection pool for the whole app lifetime (Decision in
    # Phase 1) rather than a new connection per-request.
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(title="Streaming Chat API", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Mounted last (and after the routes above) so it only catches paths that
# don't match /health or /api/v1/*: StaticFiles(html=True) serves
# frontend/index.html for "/".
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
