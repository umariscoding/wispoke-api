"""
LiveKit access-token minting.

The dashboard's TestCallPanel calls /voice-agent/livekit-token to obtain a
short-lived LiveKit JWT scoped to a per-tenant room. The same room name +
metadata is what the worker reads via `ctx.job.metadata` to discover which
tenant it's serving.

Only token issuance lives here — the Agents runtime lives in wispoke-voice/.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from livekit import api

from app.core.config import settings
from app.core.exceptions import AppException


class LiveKitNotConfiguredError(AppException):
    """Raised when LIVEKIT_* env vars are missing — surfaces a clear 503."""

    def __init__(self) -> None:
        super().__init__(
            "Voice agent is not configured on this server. "
            "Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET.",
            status_code=503,
        )


@dataclass(frozen=True)
class LiveKitTokenResponse:
    """Shape returned to the dashboard. JSON-serializable via dataclasses.asdict()."""

    token: str
    url: str
    room_name: str
    identity: str


def _require_livekit_config() -> tuple[str, str, str]:
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise LiveKitNotConfiguredError()
    return settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret


# Agent name registered by the worker (livekit-agents @server.rtc_session).
# When this name is set on the worker, LiveKit Cloud requires *explicit
# dispatch* — auto-dispatch only fires for nameless workers. We attach a
# RoomAgentDispatch to the AccessToken so the room creation triggers the
# correct worker to join.
AGENT_NAME = "wispoke-booking-agent"


def mint_browser_token(
    *,
    company_id: str,
    identity_email: str,
    language: str = "en",
    ttl_minutes: int = 10,
) -> LiveKitTokenResponse:
    """Create a LiveKit access token for a dashboard test call.

    The room name encodes the tenant for traceability. The agent dispatch
    metadata is what the worker reads via `ctx.job.metadata` — this is what
    tells the worker which tenant to load config for.

    A fresh `session_id` per token prevents two open tabs from colliding on
    the same room.
    """
    url, api_key, api_secret = _require_livekit_config()

    session_id = uuid.uuid4().hex
    room_name = f"tenant_{company_id}_{session_id}"
    identity = f"dashboard:{identity_email}:{session_id[:8]}"

    metadata = json.dumps(
        {
            "company_id": company_id,
            "session_id": session_id,
            "language": language,
            "source": "browser",
        }
    )

    # Explicit agent dispatch — required because the worker registers with an
    # `agent_name`. Without this the room would be created but no worker
    # would join it.
    room_config = api.RoomConfiguration(
        agents=[
            api.RoomAgentDispatch(
                agent_name=AGENT_NAME,
                metadata=metadata,
            )
        ]
    )

    token = (
        api.AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity(identity)
        .with_name(identity_email)
        .with_metadata(metadata)
        .with_room_config(room_config)
        .with_ttl(timedelta(minutes=ttl_minutes))
        .with_grants(
            api.VideoGrants(
                room=room_name,
                room_join=True,
                room_create=True,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )

    return LiveKitTokenResponse(token=token, url=url, room_name=room_name, identity=identity)
