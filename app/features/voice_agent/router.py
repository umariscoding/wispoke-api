"""
Voice Agent — dashboard-facing HTTP endpoints.

Routes here are user/company-authenticated. Worker callbacks live under
/voice/internal/* (see app/features/voice_internal/router.py).
"""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import UserContext, get_current_company
from app.features.phone_numbers import repository as phone_repo
from app.features.voice_agent import call_log_repository, livekit_token, service
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
