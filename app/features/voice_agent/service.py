"""
Voice Agent — business logic for dashboard-facing settings.

Read paths return the persisted row merged on top of sensible defaults so
empty-state tenants still get a working baseline. Write paths upsert through
the repository which transparently drops any unknown columns (lets the
dashboard ship new fields before migrations land).
"""

import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.database import db
from app.features.voice_agent import repository as repo

logger = logging.getLogger("wispoke.voice")


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
    "tts_provider": "deepgram",
    "voice_model": "aura-2-thalia-en",  # Deepgram Aura-2 default (lowest TTFB)
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


# ─── Call recordings ────────────────────────────────────────────────────────


def sign_recording_url(object_key: str, *, expires_in: int = 3600) -> Optional[str]:
    """Mint a short-lived signed URL for a recording in the private bucket.

    Recordings live in a private Supabase Storage bucket (they're call audio —
    PII), so we never expose a permanent URL. The worker stores only the object
    key; the dashboard calls this per-playback to get a temporary link.

    Returns None on failure (e.g. object missing) so the caller can 404.
    """
    try:
        res = db.storage.from_(settings.recording_bucket).create_signed_url(
            object_key, expires_in
        )
        if isinstance(res, dict):
            # supabase-py has used a few key spellings across versions.
            return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        return None
    except Exception:
        logger.exception("failed to sign recording url for key=%s", object_key)
        return None
