from fastapi import FastAPI
from app.api.v1.router import api_router
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(title="Streaming Chat API")
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}