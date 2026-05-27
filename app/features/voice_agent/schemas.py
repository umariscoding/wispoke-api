"""
Voice Agent — Pydantic schemas (dashboard-facing).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class VoiceAgentSettingsRequest(BaseModel):
    """Partial-update payload for /voice-agent/settings.

    Every field is optional — the service-layer upsert merges with what's
    already stored. Provider fields are constrained to the enum values the
    DB CHECK constraints accept (see migration 010).
    """

    # Agent identity & flow
    is_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    business_phone: Optional[str] = None
    system_prompt: Optional[str] = None
    appointment_duration_min: Optional[int] = Field(default=None, ge=5, le=480)
    appointment_fields: Optional[List[str]] = None

    # Locale
    language: Optional[str] = None  # ISO 639-1 ("en", "da")
    timezone: Optional[str] = None  # IANA tz name (e.g. "Europe/Copenhagen")

    # Provider abstraction — must match migration 010's CHECK constraints
    stt_provider: Optional[str] = Field(default=None, pattern="^(deepgram|speechmatics)$")
    llm_provider: Optional[str] = Field(default=None, pattern="^(openai|anthropic)$")
    tts_provider: Optional[str] = Field(default=None, pattern="^(elevenlabs|cartesia|azure)$")

    # Model selection (free-form strings; validated by the worker at session start)
    voice_model: Optional[str] = None  # e.g. ElevenLabs voice_id
    llm_model: Optional[str] = None  # e.g. "gpt-4o", "claude-sonnet-4-5"
