"""
Voice Agent — HTTP and WebSocket endpoints.

Handles:
- Settings CRUD (authenticated)
- Deepgram Agent API WebSocket proxy (browser testing)
- Twilio incoming call webhook (production)
- WebSocket media stream handler (called by Twilio)
"""

import logging
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.voice_agent import service
from app.features.voice_agent.schemas import VoiceAgentSettingsRequest
from app.features.voice_agent.stream_handler import VoiceStreamHandler
from app.features.voice_agent.agent_handler import handle_agent_ws
from app.features.availability.service import get_available_slots_for_date
from app.features.appointments.service import create_appointment

logger = logging.getLogger("wispoke.voice")

router = APIRouter(prefix="/voice-agent", tags=["voice-agent"])


# ---------------------------------------------------------------------------
# Settings CRUD (authenticated)
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings(current_user: UserContext = Depends(get_current_company)):
    return service.get_settings(current_user.company_id)


@router.put("/settings")
async def update_settings(body: VoiceAgentSettingsRequest, current_user: UserContext = Depends(get_current_company)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return service.update_settings(current_user.company_id, data)


# ---------------------------------------------------------------------------
# Deepgram Agent API — browser test call
# ---------------------------------------------------------------------------

@router.get("/agent-config")
async def get_agent_config(current_user: UserContext = Depends(get_current_company)):
    """Return the Deepgram Agent API config (without API keys) for debugging."""
    from app.features.voice_agent.agent_handler import build_agent_config
    from app.features.voice_agent.repository import get_settings as get_va_settings

    va_settings = get_va_settings(current_user.company_id)
    if not va_settings:
        va_settings = {}

    config = build_agent_config(current_user.company_id, va_settings)
    # Strip any API keys before returning
    if "agent" in config and "think" in config["agent"]:
        config["agent"]["think"]["provider"].pop("api_key", None)
    return config


@router.websocket("/agent/{company_id}")
async def agent_websocket(websocket: WebSocket, company_id: str, token: str = ""):
    """
    Browser connects here for test calls.
    Validates JWT token via query param (?token=...) before accepting.
    """
    # Authenticate — browser WS can't send headers, so token is in query string
    from app.core.security import get_current_user_info
    user_info = get_current_user_info(token) if token else None
    if not user_info or user_info.get("user_type") != "company":
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Verify the token's company matches the requested company_id
    token_company = user_info.get("company_id")
    if token_company != company_id:
        await websocket.close(code=4003, reason="Forbidden")
        return

    await websocket.accept()
    logger.info(f"Agent test call started for company: {company_id}")

    from app.features.voice_agent.repository import get_settings as get_va_settings
    va_settings = get_va_settings(company_id) or {}

    try:
        await handle_agent_ws(websocket, company_id, va_settings)
    except WebSocketDisconnect:
        logger.info(f"Agent test call ended for company: {company_id}")
    except Exception as e:
        logger.error(f"Agent test call error: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Twilio incoming call webhook (public — called by Twilio)
# ---------------------------------------------------------------------------

@router.post("/twilio/incoming")
async def twilio_incoming_call(request: Request):
    """
    Twilio hits this URL when a call comes in.
    Returns TwiML that connects the call to our WebSocket media stream.
    """
    form = await request.form()
    called_number = form.get("Called", "")
    call_sid = form.get("CallSid", "")

    logger.info(f"Incoming call to {called_number}, CallSid: {call_sid}")

    # Look up which company owns this phone number
    settings = service.get_settings_for_call(called_number)
    if not settings:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, this number is not configured for automated scheduling. Goodbye.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Build WebSocket URL for media stream
    base_url = str(request.base_url).rstrip("/")
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/voice-agent/media-stream/{settings['company_id']}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="company_id" value="{settings['company_id']}" />
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# WebSocket media stream (called by Twilio <Stream>)
# ---------------------------------------------------------------------------

@router.websocket("/media-stream/{company_id}")
async def media_stream(websocket: WebSocket, company_id: str):
    """
    Twilio connects here to stream call audio.
    We run the full STT → LLM → TTS pipeline in real time.
    """
    await websocket.accept()
    logger.info(f"Media stream connected for company: {company_id}")

    # Load voice agent settings
    from app.features.voice_agent.repository import get_settings as get_va_settings
    va_settings = get_va_settings(company_id)

    if not va_settings or not va_settings.get("is_enabled"):
        logger.warning(f"Voice agent not enabled for company: {company_id}")
        await websocket.close()
        return

    system_prompt = service.build_system_prompt(va_settings)

    async def get_slots(cid: str, date_str: str):
        return get_available_slots_for_date(cid, date_str, va_settings.get("appointment_duration_min", 30))

    async def book_appt(cid: str, action: dict):
        from datetime import datetime, timedelta
        start = datetime.strptime(action["start_time"], "%H:%M")
        duration = va_settings.get("appointment_duration_min", 30)
        end = start + timedelta(minutes=duration)

        appt_data = {
            "caller_name": action.get("caller_name"),
            "caller_phone": action.get("caller_phone"),
            "scheduled_date": action["scheduled_date"],
            "start_time": action["start_time"],
            "end_time": end.strftime("%H:%M"),
            "duration_min": duration,
            "service_type": action.get("service_type"),
            "source": "voice_agent",
        }
        return create_appointment(cid, appt_data)

    handler = VoiceStreamHandler(
        company_id=company_id,
        system_prompt=system_prompt,
        greeting_message=va_settings.get("greeting_message", "Hello! How can I help you today?"),
        voice_model=va_settings.get("voice_model", "aura-asteria-en"),
        language=va_settings.get("language", "en"),
        available_slots_fn=get_slots,
        book_appointment_fn=book_appt,
    )

    try:
        await handler.handle_twilio_ws(websocket)
    except WebSocketDisconnect:
        logger.info(f"Media stream disconnected for company: {company_id}")
    except Exception as e:
        logger.error(f"Media stream error: {e}", exc_info=True)
