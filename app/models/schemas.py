from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Existing session id to continue a conversation. Omit to start a new session.",
    )
    message: str = Field(min_length=1, description="The user's message.")


class ChatChunk(BaseModel):
    """Documents the shape of a `chunk` SSE event's `data` payload."""

    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]


class CacheStats(BaseModel):
    hits: int
    misses: int
    hit_rate: float
