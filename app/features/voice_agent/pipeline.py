"""
Voice pipeline — Gemini Live (speech-to-speech) over browser WebRTC.

Single backend: Gemini Live native audio. ~300ms latency, native turn-taking,
no separate STT/TTS. Browser-only (16/24kHz audio). Twilio support was
removed — phone calls would need a separate cascaded pipeline (Gemini Live
needs 16kHz+, Twilio is 8kHz mu-law).
"""

from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from google.genai.types import ThinkingConfig
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.utils import create_stream_resampler, mix_audio
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    LLMRunFrame,
    OutputAudioRawFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app.core.config import settings as app_settings
from app.features.voice_agent.agent_context import (
    FIELD_DEFS,
    build_system_prompt,
    spoken_date as _spoken_date,
    spoken_time as _spoken_time,
)
from app.features.voice_agent.call_log_repository import (
    create_call_log,
    finalize_call_log,
)
from app.features.voice_agent.recording_storage import (
    encode_pcm_to_wav,
    upload_recording,
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
    """Native-audio models still sometimes echo dictated emails verbatim
    ("umar at gmail dot com"). Same fix a human would apply when typing
    what they heard."""
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


def _validate_booking_date(scheduled_date: str) -> Optional[str]:
    """Return an error string if the date is bogus, else None.

    Catches the most common hallucination — booking dates in the past or
    way in the future — before the appointment hits the DB."""
    try:
        d = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
    except ValueError:
        return "scheduled_date must be YYYY-MM-DD"
    today = datetime.now(timezone.utc).date()
    if d < today:
        return f"date {scheduled_date} is in the past (today is {today.isoformat()})"
    if (d - today).days > 60:
        return f"date {scheduled_date} is more than 60 days out — please pick a closer date"
    return None


def _make_book_handler(
    company_id: str,
    va_settings: Dict[str, Any],
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
):
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)

        if "caller_email" in args:
            args["caller_email"] = _sanitize_email(args.get("caller_email"))
        if "caller_phone" in args:
            args["caller_phone"] = _sanitize_phone(args.get("caller_phone"))

        if not args.get("scheduled_date") or not args.get("start_time") or not args.get("caller_name"):
            await params.result_callback(
                {"success": False, "message": "Missing caller_name, scheduled_date, or start_time"}
            )
            return

        date_err = _validate_booking_date(args["scheduled_date"])
        if date_err:
            logger.warning(f"book_appointment date rejected for {company_id}: {date_err}")
            await params.result_callback(
                {
                    "success": False,
                    "reason": date_err,
                    "message": (
                        f"Booking failed: {date_err}. Apologize, restate today's date, "
                        "and ask the caller to confirm which day they actually want."
                    ),
                }
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

        try:
            _send_booking_emails(company_id, va_settings, args, result)
        except Exception:
            logger.exception("booking email dispatch failed")

        if on_booked:
            try:
                await on_booked(result)
            except Exception:
                logger.exception("on_booked callback failed")

        await params.result_callback(
            {
                "success": True,
                "message": (
                    f'Say exactly: "Booked — {args.get("caller_name")} on '
                    f'{_spoken_date(args["scheduled_date"])} at '
                    f'{_spoken_time(args["start_time"])}. See you then!"'
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
    biz_phone = va_settings.get("business_phone")
    caller_name = args.get("caller_name") or "there"
    caller_email = args.get("caller_email")
    caller_phone = args.get("caller_phone")
    service = args.get("service_type")
    notes = args.get("notes") or args.get("caller_address")

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
# Recording helpers — capture per-turn timestamps for transcript/audio sync
# ---------------------------------------------------------------------------

class _CallRecorder(FrameProcessor):
    """Inline recorder + turn timestamper.

    Captures user `InputAudioRawFrame` and bot `OutputAudioRawFrame`
    (Gemini Live emits `TTSAudioRawFrame`, a subclass) into per-track byte
    buffers — resampled to a common rate AND padded with silence to keep
    both tracks aligned to the wall clock. Without the silence-padding
    step the playback collapses gaps (it sounds like "all bot, then all
    user") because audio frames only arrive while a side is speaking.

    Pipecat's `AudioBufferProcessor` failed silently with Gemini Live, so
    we own this path end-to-end.

    Also records `(role, elapsed_seconds)` on each turn boundary so the
    admin UI can seek the audio player when a transcript line is clicked.
    """

    # 16-bit signed PCM = 2 bytes per sample.
    _BYTES_PER_SAMPLE = 2

    def __init__(
        self,
        target_sample_rate: int,
        turn_events: List[Tuple[str, float]],
        t0_holder: Dict[str, Optional[float]],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._target_sr = target_sample_rate
        self._user_buf = bytearray()
        self._bot_buf = bytearray()
        self._user_resampler = create_stream_resampler()
        self._bot_resampler = create_stream_resampler()
        self._turn_events = turn_events
        self._t0_holder = t0_holder
        self._frame_counts = {"user_audio": 0, "bot_audio": 0}
        self._first_user_logged = False
        self._first_bot_logged = False

    def _expected_byte_offset(self, t0: float) -> int:
        """Bytes into the buffer that wall-clock-now corresponds to."""
        elapsed = max(0.0, time.monotonic() - t0)
        return int(elapsed * self._target_sr) * self._BYTES_PER_SAMPLE

    @staticmethod
    def _pad_to(buf: bytearray, target_bytes: int) -> None:
        if len(buf) < target_bytes:
            buf.extend(b"\x00" * (target_bytes - len(buf)))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Turn timestamps for the transcript-seek feature.
        t0 = self._t0_holder.get("t")
        if t0 is not None:
            elapsed = max(0.0, time.monotonic() - t0)
            if isinstance(frame, UserStartedSpeakingFrame):
                self._turn_events.append(("user", elapsed))
            elif isinstance(frame, BotStartedSpeakingFrame):
                self._turn_events.append(("assistant", elapsed))

        # Audio capture. InputAudioRawFrame is a SystemFrame, not an
        # OutputAudioRawFrame, so we check them as separate branches.
        if isinstance(frame, InputAudioRawFrame) and t0 is not None:
            self._frame_counts["user_audio"] += 1
            if not self._first_user_logged:
                logger.info(
                    "voice_agent recording: first user audio frame "
                    "(sr=%d, %d bytes)",
                    frame.sample_rate, len(frame.audio or b""),
                )
                self._first_user_logged = True
            try:
                resampled = await self._user_resampler.resample(
                    frame.audio, frame.sample_rate, self._target_sr
                )
                if resampled:
                    self._pad_to(self._user_buf, self._expected_byte_offset(t0))
                    self._user_buf.extend(resampled)
            except Exception:
                logger.exception("voice_agent recording: user resample failed")
        elif isinstance(frame, OutputAudioRawFrame) and t0 is not None:
            self._frame_counts["bot_audio"] += 1
            if not self._first_bot_logged:
                logger.info(
                    "voice_agent recording: first bot audio frame "
                    "(type=%s, sr=%d, %d bytes)",
                    type(frame).__name__, frame.sample_rate, len(frame.audio or b""),
                )
                self._first_bot_logged = True
            try:
                resampled = await self._bot_resampler.resample(
                    frame.audio, frame.sample_rate, self._target_sr
                )
                if resampled:
                    self._pad_to(self._bot_buf, self._expected_byte_offset(t0))
                    self._bot_buf.extend(resampled)
            except Exception:
                logger.exception("voice_agent recording: bot resample failed")

        await self.push_frame(frame, direction)

    def merged_pcm(self) -> bytes:
        """Mix user + bot tracks into a single mono PCM stream.

        Both buffers are wall-clock-aligned (silence-padded as frames arrived),
        so a simple sample-wise mix produces the correct interleaved playback.
        """
        # Final equalization — pad whichever buffer ended early so mix doesn't
        # truncate the longer side's tail.
        max_len = max(len(self._user_buf), len(self._bot_buf))
        self._pad_to(self._user_buf, max_len)
        self._pad_to(self._bot_buf, max_len)

        logger.info(
            "voice_agent recording: finalizing — user=%d bytes (%d frames), "
            "bot=%d bytes (%d frames)",
            len(self._user_buf), self._frame_counts["user_audio"],
            len(self._bot_buf), self._frame_counts["bot_audio"],
        )
        if not self._user_buf and not self._bot_buf:
            return b""
        return mix_audio(bytes(self._user_buf), bytes(self._bot_buf))


def _attach_timestamps(
    transcript: List[Dict[str, Any]],
    turn_events: List[Tuple[str, float]],
) -> List[Dict[str, Any]]:
    user_times = [t for r, t in turn_events if r == "user"]
    asst_times = [t for r, t in turn_events if r == "assistant"]
    ui = ai = 0
    out: List[Dict[str, Any]] = []
    for entry in transcript:
        e = dict(entry)
        role = e.get("role")
        if role == "user" and ui < len(user_times):
            e["t"] = round(user_times[ui], 2)
            ui += 1
        elif role == "assistant" and ai < len(asst_times):
            e["t"] = round(asst_times[ai], 2)
            ai += 1
        elif role == "tool_call" and ai > 0:
            e["t"] = round(asst_times[ai - 1], 2)
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Gemini Live pipeline
# ---------------------------------------------------------------------------

# Gemini Live's catalog of TTS voices. The dashboard prefixes the stored value
# with `gemini-` so we can route by provider; we strip the prefix here.
_GEMINI_VOICES = {"aoede", "charon", "fenrir", "kore", "puck"}

# Default Gemini Live model. Per-tenant override available via
# voice_agent_settings.llm_model (the dashboard picker writes there).
# Bump this when Google ships a newer GA Live model.
DEFAULT_GEMINI_LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# Model IDs the dashboard exposes. Anything else gets coerced to the default
# so a stale/typo'd setting can't crash the pipeline.
SUPPORTED_GEMINI_LIVE_MODELS = {
    "gemini-2.5-flash-native-audio-preview-12-2025",  # Recommended
    "gemini-2.5-flash-native-audio-preview-09-2025",  # Older preview
    "gemini-3.1-flash-live-preview",                  # Experimental, lowest latency
}


def _resolve_model(va_settings: Dict[str, Any]) -> str:
    requested = (va_settings.get("llm_model") or "").strip()
    if requested in SUPPORTED_GEMINI_LIVE_MODELS:
        return requested
    return DEFAULT_GEMINI_LIVE_MODEL


def _resolve_gemini_voice(voice_model: Optional[str]) -> str:
    """Pick the Gemini voice id from the saved `voice_model` setting.

    Falls back to Aoede if blank or set to a legacy non-Gemini voice."""
    raw = (voice_model or "").strip().lower()
    if raw.startswith("gemini-"):
        name = raw.removeprefix("gemini-")
        if name in _GEMINI_VOICES:
            return name.capitalize()
    return "Aoede"


def _build_gemini_task(
    company_id: str,
    va_settings: Dict[str, Any],
    transport: BaseTransport,
    *,
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    extra_processors: Optional[List[FrameProcessor]] = None,
) -> Tuple[PipelineTask, LLMContext]:
    """Single-service pipeline using Gemini Live's native speech-to-speech.

    Silero VAD feeds the user-side context aggregator; Gemini's own server-side
    turn detection drives end-of-turn signaling.
    """
    gemini_key = app_settings.gemini_api_key
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    tools = ToolsSchema(standard_tools=[_book_appointment_schema(va_settings)])

    system_prompt = build_system_prompt(company_id, va_settings)
    greeting = (va_settings.get("greeting_message") or "").strip() or (
        "Hello! Thanks for calling. How can I help you today?"
    )
    full_prompt = (
        f"{system_prompt}\n\n# First Words\n"
        f'Begin the call by saying exactly: "{greeting}"'
    )

    # Small thinking budget gives the model room for date arithmetic and
    # tool-arg structuring (the booking turn is where hallucinations hurt
    # most). 0 was fastest TTFT but caused wrong-day bookings.
    model = _resolve_model(va_settings)
    llm = GeminiLiveLLMService(
        api_key=gemini_key,
        settings=GeminiLiveLLMService.Settings(
            model=model,
            voice=_resolve_gemini_voice(va_settings.get("voice_model")),
            system_instruction=full_prompt,
            thinking=ThinkingConfig(thinking_budget=256),
        ),
    )
    logger.info("voice_agent: using Gemini Live model=%s", model)
    llm.register_function(
        "book_appointment", _make_book_handler(company_id, va_settings, on_booked)
    )

    context = LLMContext(messages=[], tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # extra_processors (audio_buffer + timestamper) MUST sit between `llm`
    # and `transport.output()`. transport.output() consumes OutputAudioRawFrame
    # (and its TTSAudioRawFrame subclass that GeminiLiveLLMService emits) —
    # it routes the frame to the WebRTC sender's queue but never pushes it
    # downstream. So anything placed after transport.output() never sees bot
    # audio, which is why call recordings were silent on the bot side.
    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            *(extra_processors or []),
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


def _serialize_transcript(messages: List[Any]) -> List[Dict[str, Any]]:
    """Reduce LLMContext messages to {role, content} pairs for the DB."""
    out: List[Dict[str, Any]] = []
    for m in messages:
        role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) or "unknown"
        if role == "system":
            continue
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(content, list):
            text = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        elif isinstance(content, str):
            text = content
        else:
            text = ""
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
    audio_in_sample_rate: int,
    audio_out_sample_rate: int,
    caller_ref: Optional[str] = None,
) -> None:
    """Run loop for a browser call. Owns greeting, recording, transcript save."""
    started_at = datetime.now(timezone.utc)
    call_log_id = create_call_log(company_id, source="browser", caller_ref=caller_ref)
    booked_appointment_id: Dict[str, Optional[str]] = {"id": None}

    async def on_booked(appt: Dict[str, Any]) -> None:
        booked_appointment_id["id"] = appt.get("appointment_id")

    # Record at the input sample rate (16kHz) — bot audio is resampled down
    # from Gemini's 24kHz output. 16kHz mono PCM is ~30KB/sec, plenty for voice.
    recording_rate = audio_in_sample_rate
    turn_events: List[Tuple[str, float]] = []
    t0_holder: Dict[str, Optional[float]] = {"t": None}
    recorder = _CallRecorder(
        target_sample_rate=recording_rate,
        turn_events=turn_events,
        t0_holder=t0_holder,
    )

    task, context = _build_gemini_task(
        company_id,
        va_settings,
        transport,
        audio_in_sample_rate=audio_in_sample_rate,
        audio_out_sample_rate=audio_out_sample_rate,
        on_booked=on_booked,
        extra_processors=[recorder],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_t, _c):
        t0_holder["t"] = time.monotonic()
        logger.info("voice_agent recording: call %s started", call_log_id)
        # Gemini Live speaks the greeting via the model itself (steered by the
        # "First Words" section in the system prompt). LLMRunFrame triggers
        # the initial inference once the WebRTC peer is ready.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_t, _c):
        try:
            recording_url: Optional[str] = None
            recording_format: Optional[str] = None
            pcm = recorder.merged_pcm()
            logger.info(
                "voice_agent recording: collected %d PCM bytes for call %s",
                len(pcm), call_log_id,
            )
            if pcm:
                try:
                    wav = encode_pcm_to_wav(pcm, sample_rate=recording_rate, num_channels=1)
                    recording_url = upload_recording(company_id, call_log_id, wav)
                    if recording_url:
                        recording_format = "wav"
                        logger.info("voice_agent recording uploaded: %s", recording_url)
                    else:
                        logger.warning("voice_agent recording upload returned None")
                except Exception:
                    logger.exception("Failed to encode/upload call recording")
            else:
                logger.warning(
                    "voice_agent recording: no audio captured for call %s",
                    call_log_id,
                )

            transcript = _attach_timestamps(
                _serialize_transcript(list(context.messages)),
                turn_events,
            )
            finalize_call_log(
                call_log_id,
                transcript=transcript,
                started_at=started_at,
                appointment_id=booked_appointment_id["id"],
                recording_url=recording_url,
                recording_format=recording_format,
            )
        finally:
            await task.cancel()

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    await runner.run(task)


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
    """Process a SmallWebRTC SDP offer and start the pipeline."""

    async def _on_connection(connection: SmallWebRTCConnection) -> None:
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
        )

        import asyncio
        asyncio.create_task(
            _run_call(
                transport,
                company_id,
                va_settings,
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
            )
        )

    return await _webrtc_handler.handle_web_request(request, _on_connection)


async def handle_browser_patch(patch_request) -> None:
    """Apply trickled ICE candidates to an in-flight peer connection."""
    await _webrtc_handler.handle_patch_request(patch_request)
