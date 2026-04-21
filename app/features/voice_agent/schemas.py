"""
Voice Agent — Pydantic schemas.
"""

from typing import Optional, List
from pydantic import BaseModel


class VoiceAgentSettingsRequest(BaseModel):
    is_enabled: Optional[bool] = None
    twilio_phone_number: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    greeting_message: Optional[str] = None
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    appointment_duration_min: Optional[int] = None
    voice_provider: Optional[str] = None
    voice_model: Optional[str] = None
    language: Optional[str] = None
    system_prompt: Optional[str] = None
    appointment_fields: Optional[List[str]] = None  # e.g. ["name", "phone", "address"]
