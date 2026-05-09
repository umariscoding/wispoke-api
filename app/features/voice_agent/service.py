"""
Voice Agent — business logic.
"""

from typing import Any, Dict

from app.features.voice_agent import repository as repo


# Legacy DB columns we no longer surface to the FE — the table still has them
# (migration 004) but the code path doesn't use them anymore. Stripped from
# both reads and writes so they don't leak into the dashboard or trip the
# `voice_provider_check` constraint when echoed back.
_LEGACY_FIELDS = {"voice_provider"}


def _strip_legacy(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in _LEGACY_FIELDS}


def get_settings(company_id: str) -> Dict[str, Any]:
    settings = repo.get_settings(company_id)
    if not settings:
        return {
            "is_enabled": False,
            "greeting_message": "Hello! Thank you for calling. How can I help you today?",
            "business_name": None,
            "business_type": None,
            "business_phone": None,
            "appointment_duration_min": 30,
            "voice_model": "gemini-aoede",
            "llm_model": "gemini-2.5-flash-native-audio-preview-12-2025",
            "language": "en",
            "system_prompt": None,
            "appointment_fields": ["name", "phone"],
        }
    return _strip_legacy(settings)


def update_settings(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return _strip_legacy(repo.upsert_settings(company_id, **_strip_legacy(data)))
