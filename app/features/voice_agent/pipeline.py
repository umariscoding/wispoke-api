"""
Pipecat voice pipeline — two backends:

1. Gemini Live (browser only, when GEMINI_API_KEY is set) — speech-to-speech,
   ~300ms latency, native turn-taking. No separate STT/TTS.
2. Deepgram + Groq (default + Twilio fallback) — STT → LLM → TTS chain. Used
   when Gemini key is unset, and always for Twilio (Gemini Live needs 16/24kHz
   audio; Twilio is 8kHz).

Both backends share the same system prompt and the same `book_appointment`
tool, so behavior is consistent.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import WebSocket
from google.genai.types import ThinkingConfig
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import (
    UserTurnStrategies,
    default_user_turn_start_strategies,
)

from app.core.config import settings as app_settings
from app.features.voice_agent.agent_context import (
    FIELD_DEFS,
    build_system_prompt,
)
from app.features.voice_agent.call_log_repository import (
    create_call_log,
    finalize_call_log,
)

logger = logging.getLogger("wispoke.voice.pipecat")


# ---------------------------------------------------------------------------
# Tool: book_appointment
# ---------------------------------------------------------------------------

def _book_appointment_schema(va_settings: Dict[str, Any]) -> FunctionSchema:
    fields = va_settings.get("appointment_fields") or ["name", "phone"]
    field_labels = " AND ".join(FIELD_DEFS[f]["label"] for f in fields if f in FIELD_DEFS)

    properties: Dict[str, Any] = {
        "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD"},
        "start_time": {"type": "string", "description": "Start time in HH:MM"},
    }
    required = ["scheduled_date", "start_time"]
    for f in fields:
        fd = FIELD_DEFS.get(f)
        if fd:
            properties[fd["param"]] = {"type": "string", "description": fd["desc"]}
            required.append(fd["param"])

    return FunctionSchema(
        name="book_appointment",
        description=(
            f"Book an appointment. ONLY call AFTER collecting {field_labels}, "
            "date, time, AND confirmation. NEVER use placeholder data."
        ),
        properties=properties,
        required=required,
    )


_EMAIL_PHONETICS = {
    " at ": "@",
    " dot ": ".",
    " underscore ": "_",
    " dash ": "-",
    " hyphen ": "-",
    " zed ": "z",
    " zee ": "z",
}


def _sanitize_email(raw: Optional[str]) -> Optional[str]:
    """Clean up Deepgram artifacts in dictated emails.

    Deepgram transcribes "umar at gmail dot com" verbatim instead of normalizing
    to a real address. Also emits "zed"/"zee" for the letter Z. Apply the same
    fixes a human would when typing what they heard."""
    if not raw:
        return raw
    s = " " + raw.lower().strip() + " "
    for k, v in _EMAIL_PHONETICS.items():
        s = s.replace(k, v)
    s = s.replace(" ", "").strip(".")
    return s or None


def _sanitize_phone(raw: Optional[str]) -> Optional[str]:
    """Strip dictation noise from phone numbers — keep digits and a leading +."""
    if not raw:
        return raw
    s = raw.replace("double ", "").replace("triple ", "")
    keep = "".join(c for c in s if c.isdigit() or c == "+")
    return keep or None


def _make_book_handler(
    company_id: str,
    va_settings: Dict[str, Any],
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
):
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)

        # Clean up STT artifacts before validation/persistence.
        if "caller_email" in args:
            args["caller_email"] = _sanitize_email(args.get("caller_email"))
        if "caller_phone" in args:
            args["caller_phone"] = _sanitize_phone(args.get("caller_phone"))

        if not args.get("scheduled_date") or not args.get("start_time") or not args.get("caller_name"):
            await params.result_callback(
                {"success": False, "message": "Missing caller_name, scheduled_date, or start_time"}
            )
            return

        from app.features.appointments.service import create_appointment

        duration = va_settings.get("appointment_duration_min", 30)
        try:
            start = datetime.strptime(args["start_time"], "%H:%M")
        except ValueError:
            await params.result_callback({"success": False, "message": "start_time must be HH:MM"})
            return

        payload = {
            "caller_name": args.get("caller_name"),
            "caller_phone": args.get("caller_phone"),
            "caller_email": args.get("caller_email"),
            "scheduled_date": args["scheduled_date"],
            "start_time": args["start_time"],
            "end_time": (start + timedelta(minutes=duration)).strftime("%H:%M"),
            "duration_min": duration,
            "service_type": args.get("service_type"),
            "notes": args.get("notes") or args.get("caller_address"),
            "source": "voice_agent",
        }

        try:
            result = create_appointment(company_id, payload)
        except Exception as e:
            # Surface the real reason to the LLM so it can give the caller
            # honest feedback instead of inventing one ("slot isn't available"
            # was being hallucinated when the actual failure was something
            # else — date format, validation, etc).
            reason = str(e) or "unknown error"
            logger.warning(f"book_appointment rejected for {company_id}: {reason}")
            await params.result_callback(
                {
                    "success": False,
                    "reason": reason,
                    "message": (
                        f"Booking failed: {reason}. Tell the caller in one sentence "
                        "what went wrong, then offer the next available slot."
                    ),
                }
            )
            return

        # Best-effort booking notifications. Failures are logged but don't
        # affect the call — the LLM still hears "success".
        try:
            _send_booking_emails(company_id, va_settings, args, result)
        except Exception:
            logger.exception("booking email dispatch failed")

        if on_booked:
            try:
                await on_booked(result)
            except Exception:
                logger.exception("on_booked callback failed")

        # Tell the LLM exactly what to say. The prompt's hard-rule #5 forces
        # verbatim repetition so the caller always hears a clear confirmation.
        await params.result_callback(
            {
                "success": True,
                "message": (
                    f'Say exactly: "Booked — {args.get("caller_name")} on '
                    f'{args["scheduled_date"]} at {args["start_time"]}. See you then!"'
                ),
            }
        )

    return handler


def _send_booking_emails(
    company_id: str,
    va_settings: Dict[str, Any],
    args: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Send confirmation to caller + notification to business owner."""
    from app.core.email import send_email
    from app.core.email_templates import (
        render_caller_confirmation,
        render_owner_notification,
    )
    from app.features.auth.repository import get_company_by_id

    biz_name = va_settings.get("business_name") or "us"
    biz_phone = va_settings.get("twilio_phone_number")
    caller_name = args.get("caller_name") or "there"
    caller_email = args.get("caller_email")
    caller_phone = args.get("caller_phone")
    service = args.get("service_type")
    notes = args.get("notes") or args.get("caller_address")

    # 1. Caller confirmation
    if caller_email:
        subject, html, text = render_caller_confirmation(
            business_name=biz_name,
            caller_name=caller_name,
            scheduled_date=args["scheduled_date"],
            start_time=args["start_time"],
            service_type=service,
            business_phone=biz_phone,
        )
        send_email(to=caller_email, subject=subject, html=html, text=text)

    # 2. Business owner notification
    company = get_company_by_id(company_id)
    owner_email = (company or {}).get("email")
    if owner_email:
        subject, html, text = render_owner_notification(
            business_name=biz_name,
            caller_name=caller_name,
            caller_phone=caller_phone,
            caller_email=caller_email,
            scheduled_date=args["scheduled_date"],
            start_time=args["start_time"],
            service_type=service,
            notes=notes,
        )
        send_email(
            to=owner_email,
            subject=subject,
            html=html,
            text=text,
            reply_to=caller_email or None,
        )


# ---------------------------------------------------------------------------
# Pipeline factory (transport-agnostic)
# ---------------------------------------------------------------------------

_VOICE_REMAP = {
    "aura-asteria-en": "aura-2-andromeda-en",
    "aura-luna-en": "aura-2-aurora-en",
    "aura-orion-en": "aura-2-odysseus-en",
    "aura-helios-en": "aura-2-atlas-en",
}

# Gemini Live's catalog of TTS voices. The dashboard prefixes the stored value
# with `gemini-` so we can route by provider; we strip the prefix here.
_GEMINI_VOICES = {"aoede", "charon", "fenrir", "kore", "puck"}


def _resolve_gemini_voice(voice_model: Optional[str]) -> str:
    """Pick the Gemini voice id from the saved `voice_model` setting.

    Falls back to Aoede if the user picked a Deepgram (aura-*) voice or left
    it blank — that way browser test still works without forcing them to
    re-pick on the Gemini panel."""
    raw = (voice_model or "").strip().lower()
    if raw.startswith("gemini-"):
        name = raw.removeprefix("gemini-")
        if name in _GEMINI_VOICES:
            return name.capitalize()
    return "Aoede"


def _resolve_deepgram_voice(voice_model: Optional[str]) -> str:
    """Pick the Deepgram Aura voice id from the saved `voice_model`.

    Falls back to Andromeda if the user picked a Gemini voice."""
    raw = (voice_model or "").strip()
    if raw.startswith("aura-"):
        return _VOICE_REMAP.get(raw, raw)
    return "aura-2-andromeda-en"


def _keyterms_for(va_settings: Dict[str, Any]) -> List[str]:
    """Words to boost in Deepgram Nova-3. Domain vocab dominates STT errors —
    business names, service types, and field labels are the highest-leverage
    boosts."""
    terms: List[str] = []
    for key in ("business_name", "business_type"):
        v = (va_settings.get(key) or "").strip()
        if v:
            terms.append(v)
    for f in va_settings.get("appointment_fields") or []:
        fd = FIELD_DEFS.get(f)
        if fd:
            terms.append(fd["label"])
    # Common booking words callers say — boosts wake the model up to expect them.
    terms.extend(["appointment", "booking", "schedule", "reschedule", "cancel"])
    # Dedupe while preserving order.
    seen: set = set()
    out: List[str] = []
    for t in terms:
        k = t.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _build_task(
    company_id: str,
    va_settings: Dict[str, Any],
    transport: BaseTransport,
    *,
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
) -> Tuple[PipelineTask, LLMContext]:
    """Wire STT → LLM → TTS around the given transport."""
    deepgram_key = app_settings.deepgram_api_key
    groq_key = app_settings.groq_api_key
    if not deepgram_key:
        raise RuntimeError("DEEPGRAM_API_KEY is required")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY is required")

    stt = DeepgramSTTService(
        api_key=deepgram_key,
        live_options=LiveOptions(keyterm=_keyterms_for(va_settings)),
    )
    # llama-3.3 is non-reasoning, predictable, and fast. gpt-oss models leaked
    # their chain-of-thought into the spoken output ("we need placeholder until
    # they give... too bad") even with reasoning_effort=low — wrong family for
    # voice. Hard token cap keeps responses to a single turn.
    llm = GroqLLMService(
        api_key=groq_key,
        model=va_settings.get("llm_model") or "llama-3.3-70b-versatile",
        params=GroqLLMService.InputParams(
            temperature=0.6,
            max_completion_tokens=150,
        ),
    )

    voice = _resolve_deepgram_voice(va_settings.get("voice_model"))
    tts = DeepgramTTSService(api_key=deepgram_key, voice=voice)

    tools = ToolsSchema(standard_tools=[_book_appointment_schema(va_settings)])
    llm.register_function("book_appointment", _make_book_handler(company_id, va_settings, on_booked))

    system_prompt = build_system_prompt(company_id, va_settings)
    context = LLMContext(messages=[{"role": "system", "content": system_prompt}], tools=tools)

    # Smart Turn v3 is a small ONNX model that detects *semantic* end-of-turn,
    # not just silence — stops the agent from interrupting "uhh... let me think".
    # Silero VAD still runs for start-of-turn detection.
    turn_strategies = UserTurnStrategies(
        start=default_user_turn_start_strategies(),
        stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())],
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_turn_strategies=turn_strategies,
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
            allow_interruptions=True,
        ),
    )

    return task, context


# ---------------------------------------------------------------------------
# Gemini Live (speech-to-speech) pipeline factory
# ---------------------------------------------------------------------------

def _build_gemini_task(
    company_id: str,
    va_settings: Dict[str, Any],
    transport: BaseTransport,
    *,
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
) -> Tuple[PipelineTask, LLMContext]:
    """Single-service pipeline using Gemini Live's native speech-to-speech.

    Replaces STT → LLM → TTS with one streaming connection. Smart Turn isn't
    needed (Gemini does its own turn detection); Silero VAD still feeds the
    user-side context aggregator.
    """
    gemini_key = app_settings.gemini_api_key
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini Live")

    tools = ToolsSchema(standard_tools=[_book_appointment_schema(va_settings)])

    system_prompt = build_system_prompt(company_id, va_settings)
    greeting = (va_settings.get("greeting_message") or "").strip() or (
        "Hello! Thanks for calling. How can I help you today?"
    )
    # Gemini Live speaks via the model itself (no TTS bypass), so we steer the
    # opening line through the system prompt rather than queuing a TTS frame.
    full_prompt = (
        f"{system_prompt}\n\n# First Words\n"
        f'Begin the call by saying exactly: "{greeting}"'
    )

    llm = GeminiLiveLLMService(
        api_key=gemini_key,
        settings=GeminiLiveLLMService.Settings(
            model="gemini-2.5-flash-native-audio-preview-09-2025",
            voice=_resolve_gemini_voice(va_settings.get("voice_model")),
            system_instruction=full_prompt,
            # thinking_budget=0 = no chain-of-thought, fastest TTFT for voice.
            thinking=ThinkingConfig(thinking_budget=0),
        ),
    )
    llm.register_function(
        "book_appointment", _make_book_handler(company_id, va_settings, on_booked)
    )

    context = LLMContext(messages=[], tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
            allow_interruptions=True,
        ),
    )
    return task, context


# ---------------------------------------------------------------------------
# Twilio entry point
# ---------------------------------------------------------------------------

def _serialize_transcript(messages: List[Any]) -> List[Dict[str, Any]]:
    """Reduce LLMContext messages to {role, content} pairs for the DB.

    OpenAI/Groq message shapes vary (string content vs list-of-parts) so we
    flatten to a string. Tool-call requests/results land as their own roles."""
    out: List[Dict[str, Any]] = []
    for m in messages:
        # Each message is a dict-like with at least "role"; "content" may be
        # str, list of parts, or absent (function-call requests).
        role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) or "unknown"
        if role == "system":
            continue  # don't persist the giant system prompt with every call
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(content, list):
            text = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        elif isinstance(content, str):
            text = content
        else:
            text = ""
        # Capture tool calls too, in a compact form
        tool_calls = m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", {})
                name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
                args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", "")
                out.append({"role": "tool_call", "content": f"{name}({args})"})
        if text:
            out.append({"role": role, "content": text})
    return out


async def _run_call(
    transport: BaseTransport,
    company_id: str,
    va_settings: Dict[str, Any],
    *,
    source: str,
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    caller_ref: Optional[str] = None,
) -> None:
    """Shared run loop for browser + Twilio. Owns greeting, transcript save."""
    started_at = datetime.now(timezone.utc)
    call_log_id = create_call_log(company_id, source=source, caller_ref=caller_ref)
    booked_appointment_id: Dict[str, Optional[str]] = {"id": None}

    async def on_booked(appt: Dict[str, Any]) -> None:
        booked_appointment_id["id"] = appt.get("appointment_id")

    # Browser + Gemini key set → use speech-to-speech. Twilio (8kHz) and the
    # no-Gemini-key case fall back to the Deepgram + Groq chain.
    use_gemini = source == "browser" and bool(app_settings.gemini_api_key)
    builder = _build_gemini_task if use_gemini else _build_task
    task, context = builder(
        company_id,
        va_settings,
        transport,
        audio_in_sample_rate=audio_in_sample_rate,
        audio_out_sample_rate=audio_out_sample_rate,
        on_booked=on_booked,
    )

    greeting = (va_settings.get("greeting_message") or "").strip() or (
        "Hello! Thanks for calling. How can I help you today?"
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_t, _c):
        if use_gemini:
            # Gemini Live speaks the greeting via the model itself (steered by
            # the "First Words" section in the system prompt). LLMRunFrame
            # triggers the initial inference once the WebRTC peer is ready.
            await task.queue_frames([LLMRunFrame()])
        else:
            # Bypass the LLM for the opening line so the user-configured
            # greeting is spoken VERBATIM via TTS. `append_to_context=True`
            # records it as the assistant's first turn so the LLM doesn't
            # greet again on the next turn.
            await task.queue_frames([
                TTSSpeakFrame(text=greeting, append_to_context=True),
            ])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_t, _c):
        try:
            transcript = _serialize_transcript(list(context.messages))
            finalize_call_log(
                call_log_id,
                transcript=transcript,
                started_at=started_at,
                appointment_id=booked_appointment_id["id"],
            )
        finally:
            await task.cancel()

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    await runner.run(task)


async def run_twilio_call(
    websocket: WebSocket,
    company_id: str,
    va_settings: Dict[str, Any],
) -> None:
    """Bridge a Twilio media stream through the Pipecat pipeline."""
    _, call_data = await parse_telephony_websocket(websocket)

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=va_settings.get("twilio_account_sid") or "",
        auth_token=va_settings.get("twilio_auth_token") or "",
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await _run_call(
        transport,
        company_id,
        va_settings,
        source="twilio",
        audio_in_sample_rate=8000,
        audio_out_sample_rate=8000,
        caller_ref=call_data.get("call_id"),
    )


# ---------------------------------------------------------------------------
# Browser SmallWebRTC entry point
# ---------------------------------------------------------------------------

# One handler per process — it tracks the in-flight peer connections so SDP
# renegotiation / trickle-ICE patches land on the right session.
_webrtc_handler = SmallWebRTCRequestHandler(
    ice_servers=[IceServer(urls="stun:stun.l.google.com:19302")]
)


async def handle_browser_offer(
    request: SmallWebRTCRequest,
    company_id: str,
    va_settings: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """Process a SmallWebRTC SDP offer and start the pipeline.

    Returns the SDP answer payload that the browser client expects (sdp, type,
    pc_id). The Pipecat pipeline runs as a background task tied to the
    connection's lifecycle — closing the peer connection cancels the task.
    """

    async def _on_connection(connection: SmallWebRTCConnection) -> None:
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        )

        # Run the pipeline in the background so the offer endpoint can return
        # its SDP answer immediately.
        import asyncio
        asyncio.create_task(
            _run_call(
                transport,
                company_id,
                va_settings,
                source="browser",
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
            )
        )

    return await _webrtc_handler.handle_web_request(request, _on_connection)


async def handle_browser_patch(patch_request) -> None:
    """Apply trickled ICE candidates to an in-flight peer connection."""
    await _webrtc_handler.handle_patch_request(patch_request)
