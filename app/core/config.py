"""
Application settings — single source of truth for all configuration.

Uses pydantic-settings to load from environment variables / .env file.
Required settings raise a validation error at startup if missing.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # --- Required secrets (no defaults — app won't start without them) ---
    supabase_url: str
    supabase_key: str
    jwt_secret_key: str
    pinecone_api_key: str
    cohere_api_key: str

    # --- Google OAuth ---
    google_client_id: Optional[str] = None

    # --- LLM provider keys (at least one should be set) ---
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # --- Voice Agent (Deepgram STT/TTS) ---
    deepgram_api_key: Optional[str] = None

    # --- JWT ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32 or v.startswith("your-"):
            raise ValueError(
                "jwt_secret_key must be at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    # --- AI / Embeddings ---
    embedding_model: str = "embed-english-v3.0"

    # --- Domain ---
    base_domain: str = "mysite.com"
    chatbot_protocol: str = "https"
    use_subdomain_routing: bool = False

    # --- LemonSqueezy ---
    lemonsqueezy_api_key: Optional[str] = None
    lemonsqueezy_webhook_secret: Optional[str] = None
    lemonsqueezy_store_id: Optional[str] = None
    lemonsqueezy_variant_id: Optional[str] = None
    admin_dashboard_url: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — loaded once at startup."""
    return Settings()


settings = get_settings()


def get_chatbot_url(slug: str) -> str:
    """Generate the public chatbot URL for a company slug."""
    if settings.use_subdomain_routing:
        return f"{settings.chatbot_protocol}://{slug}.{settings.base_domain}"
    return f"{settings.chatbot_protocol}://{settings.base_domain}/public/chatbot/{slug}"
