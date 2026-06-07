"""
Voice Agent — dashboard-facing HTTP endpoints.

Routes here are user/company-authenticated. Worker callbacks live under
/voice/internal/* (see app/features/voice_internal/router.py).
"""

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.features.auth.dependencies import UserContext, get_current_company
from app.features.phone_numbers import repository as phone_repo
from app.features.voice_agent import call_log_repository, livekit_token, service
from app.features.voice_agent import telnyx_phones
from app.features.voice_agent.schemas import VoiceAgentSettingsRequest

logger = logging.getLogger("wispoke.voice")

router = APIRouter(prefix="/voice-agent", tags=["voice-agent"])


# ─── Settings CRUD ─────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(current_user: UserContext = Depends(get_current_company)):
    return service.get_settings(current_user.company_id)


@router.put("/settings")
async def update_settings(
    body: VoiceAgentSettingsRequest,
    current_user: UserContext = Depends(get_current_company),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return service.update_settings(current_user.company_id, data)


# ─── Phone-number marketplace (Telnyx) ─────────────────────────────────────


class ClaimNumberRequest(BaseModel):
    e164: str = Field(..., pattern=r"^\+\d{6,15}$")
    region_label: Optional[str] = None
    country: Optional[str] = "DK"
    phone_number_type: str = "local"


@router.get("/available-numbers")
async def available_numbers(
    country: str = "DK",
    phone_number_type: str = "local",
    limit: int = 10,
    _current_user: UserContext = Depends(get_current_company),
):
    """Live search of Telnyx inventory — what's available right now.

    The dashboard shows these to a company during onboarding. The company
    picks one, `POST /voice-agent/claim-number` orders it and assigns it.
    """
    limit = max(1, min(int(limit), 25))
    try:
        numbers = await telnyx_phones.search_available(
            country_code=country, phone_number_type=phone_number_type, limit=limit
        )
    except telnyx_phones.TelnyxError as e:
        logger.exception("Telnyx number search failed")
        raise HTTPException(status_code=502, detail=f"Couldn't reach Telnyx: {e}")
    return {"numbers": numbers}


@router.post("/claim-number")
async def claim_number(
    body: ClaimNumberRequest,
    current_user: UserContext = Depends(get_current_company),
):
    """Order the number from Telnyx + assign it to the current company.

    Steps:
      1. Refuse if this tenant already holds an active number (one per tenant).
      2. Order via Telnyx, bound to our FQDN SIP Connection (TELNYX_CONNECTION_ID)
         so inbound PSTN routes straight into the LiveKit SIP trunk.
      3. Insert into `phone_numbers` as `assigned` to this tenant.

    Note: DK/FR geographic orders may come back `pending` until the account's
    regulatory bundle clears — the row is still created so the dashboard can
    show "provisioning". The Telnyx order id is stored in `provider_sid`.
    """
    # Guard: one assigned number per tenant. Phase-2 may allow stacking but
    # for now keep the model "company has one number" so the dashboard's
    # display + agent routing match.
    existing = phone_repo.list_for_company(current_user.company_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This company already has an assigned number",
        )

    # We own all numbers under our own EU identity, so attach the pre-approved
    # Requirement Group for this country/type (keyed "<COUNTRY>_<type>"). Without
    # it, DK/FR orders sit in regulatory review; with it they activate cleanly.
    from app.core.config import get_settings as _get_settings

    groups = _get_settings().telnyx_requirement_groups or {}
    rg_key = f"{(body.country or 'DK').upper()}_{body.phone_number_type}"
    requirement_group_id = groups.get(rg_key)

    try:
        result = await telnyx_phones.order_number(
            body.e164, requirement_group_id=requirement_group_id
        )
    except telnyx_phones.TelnyxError as e:
        logger.exception("Telnyx number order failed")
        raise HTTPException(status_code=502, detail=f"Telnyx order failed: {e}")

    # Two-step (insert + claim) keeps the schema's status-consistency invariant
    # intact even if the second step ever fails — releasing a half-created row
    # is the easier recovery than fighting the assignment CHECK constraint.
    row = phone_repo.insert(
        e164=result["e164"],
        country=(body.country or "DK"),
        region_label=body.region_label,
        provider="telnyx",
        provider_sid=result.get("order_id"),
    )
    claimed = phone_repo.claim(row["id"], current_user.company_id)
    if not claimed:
        raise HTTPException(status_code=500, detail="Claim insert raced — retry")
    return {
        "id": claimed["id"],
        "e164": claimed["e164"],
        "region_label": claimed.get("region_label"),
        "status": claimed["status"],
        "assigned_at": claimed.get("assigned_at"),
    }


# ─── Phone numbers assigned to this tenant ─────────────────────────────────


@router.get("/phone-numbers")
async def list_phone_numbers(current_user: UserContext = Depends(get_current_company)):
    """Return the inbound numbers wired to this company.

    The dashboard's voice-agent page shows these so the operator can see
    "people call THIS number to reach your agent." Today most tenants will
    have 0 or 1; the response is a list so the same UI handles a future
    "local + toll-free" pair without a redesign.
    """
    rows = phone_repo.list_for_company(current_user.company_id)
    return {
        "phone_numbers": [
            {
                "id": r["id"],
                "e164": r["e164"],
                "country": r["country"],
                "region_label": r.get("region_label"),
                "assigned_at": r.get("assigned_at"),
            }
            for r in rows
        ]
    }


# ─── LiveKit token (browser test calls) ────────────────────────────────────


@router.post("/livekit-token")
async def issue_livekit_token(current_user: UserContext = Depends(get_current_company)):
    """Mint a short-lived LiveKit access token for the dashboard's test panel.

    Uses the tenant's currently-saved `language` so the worker dispatches with
    matching locale metadata. The room name embeds the company_id which the
    worker reads via `ctx.job.metadata` to load tenant config.
    """
    settings = service.get_settings(current_user.company_id)
    response = livekit_token.mint_browser_token(
        company_id=current_user.company_id,
        identity_email=current_user.email or current_user.company_id,
        language=settings.get("language") or "en",
    )
    return asdict(response)


# ─── Call logs (read; transcripts + outcomes) ──────────────────────────────


@router.get("/call-logs")
async def list_call_logs(
    limit: int = 25,
    offset: int = 0,
    current_user: UserContext = Depends(get_current_company),
):
    # Clamp pagination to sane bounds — guards against accidental DoS via
    # a wide ?limit=999999 from a misbehaving client.
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    page = call_log_repository.list_call_logs(current_user.company_id, limit=limit, offset=offset)
    items = page["items"]
    return {
        "call_logs": items,
        "total": page["total"],
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < page["total"],
    }


@router.get("/call-logs/{call_log_id}/recording")
async def get_call_recording_url(
    call_log_id: str,
    current_user: UserContext = Depends(get_current_company),
):
    """Return a short-lived signed URL to play back this call's recording.

    The recording lives in a private bucket; `recording_url` on the row is just
    the object key. We verify the call belongs to the caller's company, then
    mint a temporary signed URL (1h) — never a permanent link.
    """
    row = call_log_repository.get_call_log(call_log_id, current_user.company_id)
    if not row or not row.get("recording_url"):
        raise HTTPException(status_code=404, detail="No recording for this call")

    url = service.sign_recording_url(row["recording_url"])
    if not url:
        raise HTTPException(status_code=502, detail="Couldn't sign recording URL")
    return {"url": url, "format": row.get("recording_format")}
