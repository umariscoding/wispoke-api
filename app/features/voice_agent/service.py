"""
Voice Agent — business logic.
"""

from typing import Any, Dict, Optional

from app.features.voice_agent import repository as repo


def get_settings(company_id: str) -> Dict[str, Any]:
    settings = repo.get_settings(company_id)
    if not settings:
        return {
            "is_enabled": False,
            "twilio_phone_number": None,
            "greeting_message": "Hello! Thank you for calling. How can I help you today?",
            "business_name": None,
            "business_type": None,
            "appointment_duration_min": 30,
            "voice_provider": "deepgram",
            "voice_model": "aura-asteria-en",
            "language": "en",
            "system_prompt": None,
            "appointment_fields": ["name", "phone"],
        }
    settings.pop("twilio_auth_token", None)  # Never expose Twilio auth token
    return settings


def update_settings(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    result = repo.upsert_settings(company_id, **data)
    result.pop("twilio_auth_token", None)
    return result


def get_settings_for_call(phone_number: str) -> Optional[Dict[str, Any]]:
    """Look up voice agent settings by the Twilio phone number being called."""
    return repo.get_settings_by_phone(phone_number)
