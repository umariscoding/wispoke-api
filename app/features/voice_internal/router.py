"""
HTTP surface for the wispoke-voice worker.

All routes require a valid service token (HS256, separate secret). The router
is mounted under /voice/internal/* so the auth boundary is visible in URLs.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.features.voice_internal import service
from app.features.voice_internal.auth import require_service_token

router = APIRouter(prefix="/voice/internal", tags=["voice-internal"])


# ─── Schemas ───────────────────────────────────────────────────────────────


class CallLogOpenRequest(BaseModel):
    company_id: str
    room_name: str
    language: str = "en"
    llm_model: Optional[str] = None
    source: str = "browser"
    caller_ref: Optional[str] = None


class CallLogFinalizeRequest(BaseModel):
    transcript: List[Dict[str, Any]] = Field(default_factory=list)
    outcome: Optional[str] = None  # 'booked' | 'no_booking' | 'failed' | 'handoff' | 'aborted'
    appointment_id: Optional[str] = None
    latency_metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None  # ISO 8601
    recording_url: Optional[str] = None  # object key in the recordings bucket
    recording_format: Optional[str] = None  # e.g. 'ogg'


class AppointmentCreateRequest(BaseModel):
    company_id: str
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None
    scheduled_date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: Optional[str] = None  # auto-computed from duration if omitted
    duration_min: Optional[int] = None
    service_type: Optional[str] = None
    notes: Optional[str] = None


# ─── Helpers ───────────────────────────────────────────────────────────────


def _enforce_company_scope(payload: Dict[str, Any], company_id: str) -> None:
    """If the service token was minted with a company_id, reject mismatches.

    Tokens without a company_id (broad tools) are allowed through — the worker
    issues those when it doesn't yet know the tenant (e.g. SIP inbound where
    DID→tenant resolution happens in dispatch).
    """
    scoped = payload.get("company_id")
    if scoped is not None and scoped != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service token is scoped to a different company",
        )


# ─── Routes ────────────────────────────────────────────────────────────────


@router.get("/tenant/{company_id}")
def get_tenant_config(
    company_id: str,
    payload: Dict[str, Any] = Depends(require_service_token),
):
    _enforce_company_scope(payload, company_id)
    return service.get_tenant_config(company_id)


@router.get("/sip/resolve")
def resolve_sip_tenant(
    to: str,
    _payload: Dict[str, Any] = Depends(require_service_token),
):
    """Map a dialed PSTN number → tenant for SIP inbound calls.

    No company-scope check on the token: this is the call the worker makes
    *before* it knows which tenant it's serving. The auth.py module already
    documents this case ("Tokens without a company_id (broad tools) are
    allowed through — the worker issues those when it doesn't yet know the
    tenant, e.g. SIP inbound").
    """
    if not to or not to.startswith("+"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`to` must be an E.164 number starting with '+'",
        )
    return service.resolve_sip_tenant(to)


@router.get("/availability/{company_id}/slots/{date_str}")
def get_available_slots(
    company_id: str,
    date_str: str,
    duration: Optional[int] = None,
    payload: Dict[str, Any] = Depends(require_service_token),
):
    _enforce_company_scope(payload, company_id)
    slots = service.get_available_slots(company_id, date_str, duration)
    return {"date": date_str, "slots": slots}


@router.post("/appointments")
def create_appointment(
    body: AppointmentCreateRequest,
    payload: Dict[str, Any] = Depends(require_service_token),
):
    _enforce_company_scope(payload, body.company_id)
    data = body.model_dump(exclude_none=True)
    company_id = data.pop("company_id")
    return service.create_appointment(company_id, data)


@router.post("/call-logs")
def open_call_log(
    body: CallLogOpenRequest,
    payload: Dict[str, Any] = Depends(require_service_token),
):
    _enforce_company_scope(payload, body.company_id)
    call_log_id = service.open_call_log(
        body.company_id,
        room_name=body.room_name,
        language=body.language,
        llm_model=body.llm_model,
        source=body.source,
        caller_ref=body.caller_ref,
    )
    return {"call_log_id": call_log_id}


@router.patch("/call-logs/{call_log_id}")
def finalize_call_log(
    call_log_id: str,
    body: CallLogFinalizeRequest,
    payload: Dict[str, Any] = Depends(require_service_token),
):
    # Note: no per-row company scope check here — the call_log_id is opaque
    # and not enumerable. If we ever need stricter isolation, the token scope
    # check above will already gate access.
    service.finalize_call_log(
        call_log_id,
        transcript=body.transcript,
        outcome=body.outcome,
        appointment_id=body.appointment_id,
        latency_metrics=body.latency_metrics,
        started_at_iso=body.started_at,
        recording_url=body.recording_url,
        recording_format=body.recording_format,
    )
    return {"ok": True}
