"""
Voice Agent — Pydantic schemas.
"""

from typing import Optional, List
from pydantic import BaseModel


class VoiceAgentSettingsRequest(BaseModel):
    is_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    business_phone: Optional[str] = None
    appointment_duration_min: Optional[int] = None
    voice_model: Optional[str] = None  # e.g. "gemini-aoede", "gemini-puck"
    llm_model: Optional[str] = None  # Gemini Live model id; see SUPPORTED_GEMINI_LIVE_MODELS
    language: Optional[str] = None
    system_prompt: Optional[str] = None
    appointment_fields: Optional[List[str]] = None  # e.g. ["name", "phone", "address"]
