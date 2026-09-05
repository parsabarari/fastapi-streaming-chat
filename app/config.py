from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env.

    See .env.example for the full list of supported keys.
    """

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    # Leave unset to talk to OpenAI directly. Set to
    # "https://openrouter.ai/api/v1" (with an OpenRouter key in
    # openai_api_key and an OpenRouter-style model name, e.g.
    # "openai/gpt-4o-mini" or "anthropic/claude-3.5-sonnet") to route
    # through OpenRouter instead - it's OpenAI-API-compatible, so the same
    # `openai` SDK client works unchanged, just pointed elsewhere.
    openai_base_url: str | None = None
    # Optional, OpenRouter-specific: shown on openrouter.ai's public
    # rankings if you opt in. Harmless (and unused) against real OpenAI.
    app_referrer_url: str | None = None
    app_title: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    environment: str = "development"

    # Sliding window size for conversation history (Decision 7 in the roadmap).
    max_context_messages: int = 10
    # TTL for cached LLM responses (Decision 5).
    cache_ttl_seconds: int = 3600
    # TTL for a session's conversation history (auto-expire idle sessions).
    session_ttl_seconds: int = 86400

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
