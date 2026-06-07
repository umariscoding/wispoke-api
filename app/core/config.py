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

    # --- LLM provider keys (used by RAG/chat AND voice agent) ---
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # --- Voice Agent providers (consumed by wispoke-voice worker, surfaced here
    # so the API can validate that a tenant's chosen provider has a key) ---
    deepgram_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

    # --- LiveKit (token minting; the SDK lives in wispoke-voice) ---
    livekit_url: Optional[str] = None
    livekit_api_key: Optional[str] = None
    livekit_api_secret: Optional[str] = None
    # SIP URI of the LiveKit Cloud inbound trunk. The Telnyx FQDN SIP
    # Connection points its FQDN at this host so inbound PSTN routes here.
    # Format: sip:<project-subdomain>.sip.livekit.cloud
    livekit_sip_uri: Optional[str] = None
    # Dispatch rule that newly-purchased LiveKit phone numbers attach to. One
    # rule serves every tenant — per-tenant routing is by dialed number, which
    # the worker reads from the SIP participant's attributes.
    livekit_sip_dispatch_rule_id: Optional[str] = None

    # --- Telephony (Telnyx) ---
    # API key for provisioning/managing numbers via the Telnyx Numbers API.
    telnyx_api_key: Optional[str] = None
    # FQDN SIP Connection whose FQDN points at LIVEKIT_SIP_URI. Numbers are
    # assigned to this connection so inbound PSTN routes straight into LiveKit.
    telnyx_connection_id: Optional[str] = None
    # Pre-approved Requirement Group ids (one per country/type) under our own EU
    # company identity. We own all numbers, so customer self-serve orders ride on
    # these — no per-customer regulatory docs. Create once via /requirement_groups.
    # JSON map of "<COUNTRY>_<type>" → group id, e.g. {"DK_local": "...", "FR_local": "..."}.
    telnyx_requirement_groups: dict = {}

    # --- Voice service-to-service JWT (separate secret from user JWT) ---
    # Used by the voice worker to authenticate callbacks into /voice/internal/*.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    voice_service_jwt_secret: Optional[str] = None

    # --- Call recordings (private Supabase Storage bucket) ---
    # The voice worker's egress uploads audio here (over S3); the dashboard
    # mints short-lived signed URLs to play it back. Must match
    # RECORDING_BUCKET in wispoke-voice/.env.
    recording_bucket: str = "call-recordings"

    # --- Email (Resend) ---
    # When unset, send_email is a no-op so the app still runs in dev.
    resend_api_key: Optional[str] = None
    email_from: str = "onboarding@resend.dev"

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
