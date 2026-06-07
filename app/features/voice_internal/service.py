"""
Service layer for /voice/internal/* — what the worker needs to do its job.

This layer composes existing features (voice_agent settings, availability,
appointments) into worker-shaped responses. We deliberately don't expose the
raw repository tables — the worker speaks one denormalized contract, and the
API is free to refactor underneath.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import NotFoundError
from app.features.auth.repository import get_company_by_id
from app.features.availability import service as availability_service
from app.features.appointments import service as appointments_service
from app.features.phone_numbers import repository as phone_repo
from app.features.voice_agent import service as voice_agent_service
from app.features.voice_agent import call_log_repository as call_log_repo


# ─── Tenant config — what the worker loads on every new session ────────────


def get_tenant_config(company_id: str) -> Dict[str, Any]:
    """Return everything the worker needs to spin up a session for this tenant.

    The shape is denormalized on purpose: the worker should not need a second
    round-trip to learn how to greet, what voice to use, or what its business
    hours are. We bundle the static parts here; dynamic data (slots, bookings)
    is fetched per-tool-call.
    """
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError(f"Company {company_id} not found")

    va_settings = voice_agent_service.get_settings(company_id)
    weekly_schedule = availability_service.get_weekly_schedule(company_id)

    # The dashboard stores business_name on voice_agent_settings; fall back to
    # the company's display name so empty-state tenants still get sensible
    # branding without forcing them through the settings UI.
    business_name = va_settings.get("business_name") or company.get("name") or "our office"

    return {
        "company_id": company_id,
        "is_enabled": va_settings.get("is_enabled", False),
        "business_name": business_name,
        "business_type": va_settings.get("business_type"),
        "business_phone": va_settings.get("business_phone"),
        "greeting_message": va_settings.get("greeting_message"),
        "system_prompt": va_settings.get("system_prompt"),
        "language": va_settings.get("language") or "en",
        "timezone": va_settings.get("timezone") or "Europe/Copenhagen",
        "appointment_duration_min": va_settings.get("appointment_duration_min", 30),
        "appointment_fields": va_settings.get("appointment_fields") or ["name", "phone"],
        "providers": {
            "stt": va_settings.get("stt_provider") or "deepgram",
            "llm": va_settings.get("llm_provider") or "openai",
            "tts": va_settings.get("tts_provider") or "elevenlabs",
        },
        "models": {
            "voice": va_settings.get("voice_model") or "21m00Tcm4TlvDq8ikWAM",
            "llm": va_settings.get("llm_model") or "gpt-4o",
        },
        "weekly_schedule": weekly_schedule,
    }


# ─── SIP inbound — resolve dialed number → tenant ──────────────────────────


def resolve_sip_tenant(e164: str) -> Dict[str, Any]:
    """Map a dialed E.164 number to the company that owns it.

    LiveKit's SIP dispatch hands the worker a metadata blob with the called
    number (e.g. `{"called_number": "+14155551234"}`); the worker hits this
    endpoint before building the agent so the rest of the session looks
    identical to a browser-initiated call.

    Raises NotFoundError if the number isn't in our pool or isn't assigned —
    both cases mean "we shouldn't be receiving this call" and the worker will
    decline the session rather than guess a tenant.
    """
    row = phone_repo.find_by_e164(e164)
    if not row:
        raise NotFoundError(f"Phone number {e164} not in pool")
    if row.get("status") != "assigned" or not row.get("assigned_company_id"):
        raise NotFoundError(f"Phone number {e164} is not assigned to any company")

    company_id = row["assigned_company_id"]
    va_settings = voice_agent_service.get_settings(company_id) or {}
    return {
        "company_id": company_id,
        "language": va_settings.get("language") or "en",
        "e164": e164,
    }


# ─── Availability / appointments — proxied through to existing services ────


def get_available_slots(
    company_id: str, date_str: str, duration_min: Optional[int] = None
) -> List[Dict[str, str]]:
    """Worker calls this once per turn when offering times.

    We default `duration_min` from the tenant's voice_agent_settings if the
    worker doesn't pass one — keeps the tool signature on the LLM side simple.
    """
    if duration_min is None:
        cfg = voice_agent_service.get_settings(company_id)
        duration_min = cfg.get("appointment_duration_min", 30) or 30
    return availability_service.get_available_slots_for_date(company_id, date_str, duration_min)


def create_appointment(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Worker calls this only after the caller said yes to a read-back."""
    # Force `source` so we can later attribute bookings made by the voice agent
    # vs. the dashboard. The worker can't override this even if it tried.
    data = {**data, "source": "voice_agent"}
    return appointments_service.create_appointment(company_id, data)


# ─── Call log lifecycle — bracketing every session ─────────────────────────


def open_call_log(
    company_id: str,
    *,
    room_name: str,
    language: str = "en",
    llm_model: Optional[str] = None,
    source: str = "browser",
    caller_ref: Optional[str] = None,
) -> str:
    return call_log_repo.create_call_log(
        company_id,
        room_name=room_name,
        source=source,
        language=language,
        llm_model=llm_model,
        caller_ref=caller_ref,
    )


def finalize_call_log(
    call_log_id: str,
    *,
    transcript: List[Dict[str, Any]],
    outcome: Optional[str],
    appointment_id: Optional[str] = None,
    latency_metrics: Optional[Dict[str, Any]] = None,
    started_at_iso: Optional[str] = None,
    recording_url: Optional[str] = None,
    recording_format: Optional[str] = None,
) -> None:
    started_at: Optional[datetime] = None
    if started_at_iso:
        try:
            started_at = datetime.fromisoformat(started_at_iso.replace("Z", "+00:00"))
        except ValueError:
            started_at = None
    call_log_repo.finalize_call_log(
        call_log_id,
        transcript=transcript,
        outcome=outcome,
        started_at=started_at,
        appointment_id=appointment_id,
        latency_metrics=latency_metrics,
        recording_url=recording_url,
        recording_format=recording_format,
    )
