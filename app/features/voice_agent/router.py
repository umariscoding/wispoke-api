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

from app.core.config import get_settings as get_app_settings
from app.features.auth.dependencies import UserContext, get_current_company
from app.features.phone_numbers import repository as phone_repo
from app.features.voice_agent import call_log_repository, livekit_token, service
from app.features.voice_agent import livekit_phones
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


# ─── Phone-number marketplace (LiveKit) ────────────────────────────────────


class ClaimNumberRequest(BaseModel):
    e164: str = Field(..., pattern=r"^\+\d{6,15}$")
    locality: Optional[str] = None
    region: Optional[str] = None
    area_code: Optional[str] = None
    country: Optional[str] = "US"


@router.get("/available-numbers")
async def available_numbers(
    country: str = "US",
    area_code: Optional[str] = None,
    limit: int = 10,
    _current_user: UserContext = Depends(get_current_company),
):
    """Live search of LiveKit's number marketplace — what's available right now.

    The dashboard shows these to a company during onboarding. The company
    picks one, `POST /voice-agent/claim-number` purchases it and assigns it.
    """
    limit = max(1, min(int(limit), 25))
    try:
        numbers = await livekit_phones.search_numbers(
            country_code=country, area_code=area_code, limit=limit
        )
    except Exception as e:
        logger.exception("LiveKit number search failed")
        raise HTTPException(status_code=502, detail=f"Couldn't reach LiveKit: {e}")
    return {"numbers": numbers}


@router.post("/claim-number")
async def claim_number(
    body: ClaimNumberRequest,
    current_user: UserContext = Depends(get_current_company),
):
    """Purchase the number from LiveKit + assign it to the current company.

    Steps:
      1. Refuse if this tenant already holds an active number (one per tenant).
      2. Purchase via LiveKit + attach the project's dispatch rule.
      3. Insert into `phone_numbers` as `assigned` to this tenant.

    Returns 402 if LiveKit refuses on quota — that's the "upgrade required"
    signal the dashboard surfaces back to the user.
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

    app_settings = get_app_settings()
    sdr_id = app_settings.livekit_sip_dispatch_rule_id

    try:
        result = await livekit_phones.purchase_number(
            body.e164, sip_dispatch_rule_id=sdr_id
        )
    except livekit_phones.LiveKitQuotaExceeded:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "LiveKit number quota reached. Upgrade your LiveKit plan "
                "to provision additional numbers."
            ),
        )
    except Exception as e:
        logger.exception("LiveKit number purchase failed")
        raise HTTPException(status_code=502, detail=f"LiveKit purchase failed: {e}")

    # Use the locality/region the FE saw at search-time as the human label so
    # the dashboard reads "Los Angeles CA — 213" rather than just "+1213…".
    label_bits = [body.locality, body.region]
    label_bits = [b for b in label_bits if b]
    if body.area_code:
        label_bits.append(body.area_code)
    region_label = " — ".join(label_bits) if label_bits else None

    # Two-step (insert + claim) keeps the schema's status-consistency invariant
    # intact even if the second step ever fails — releasing a half-created row
    # is the easier recovery than fighting the assignment CHECK constraint.
    row = phone_repo.insert(
        e164=result["e164"],
        country=(body.country or "US"),
        region_label=region_label,
        provider="livekit",
        provider_sid=result.get("id"),
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
