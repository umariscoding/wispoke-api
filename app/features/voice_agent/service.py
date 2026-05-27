"""
Voice Agent — business logic for dashboard-facing settings.

Read paths return the persisted row merged on top of sensible defaults so
empty-state tenants still get a working baseline. Write paths upsert through
the repository which transparently drops any unknown columns (lets the
dashboard ship new fields before migrations land).
"""

from typing import Any, Dict

from app.features.voice_agent import repository as repo


# Columns the DB used to have but the v2 stack no longer surfaces. If anything
# stale slips in from an old client, we strip it on read+write so the dashboard
# never sees ghosts.
_LEGACY_FIELDS = {
    "voice_provider",  # dropped in migration 010
    "twilio_phone_number",
    "twilio_account_sid",
    "twilio_auth_token",
}

# Defaults applied when no row exists. Matches migration 010 column defaults
# so an empty-state read is indistinguishable from a freshly-inserted row.
_DEFAULTS: Dict[str, Any] = {
    "is_enabled": False,
    "greeting_message": "Hello! Thank you for calling. How can I help you today?",
    "business_name": None,
    "business_type": None,
    "business_phone": None,
    "system_prompt": None,
    "appointment_duration_min": 30,
    "appointment_fields": ["name", "phone"],
    "language": "en",
    "timezone": "Europe/Copenhagen",
    "stt_provider": "deepgram",
    "llm_provider": "openai",
    "tts_provider": "elevenlabs",
    "voice_model": "EXAVITQu4vr4xnSDxMaL",  # ElevenLabs Sarah (current premade default)
    "llm_model": "gpt-4o",
}


def _strip_legacy(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in _LEGACY_FIELDS}


def get_settings(company_id: str) -> Dict[str, Any]:
    settings = repo.get_settings(company_id)
    if not settings:
        return {**_DEFAULTS}
    # Layer defaults under whatever's persisted so a row missing a column
    # (e.g. older row predating a new field) still surfaces a usable value.
    return {**_DEFAULTS, **_strip_legacy(settings)}


def update_settings(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = _strip_legacy(data)
    return _strip_legacy(repo.upsert_settings(company_id, **cleaned))
