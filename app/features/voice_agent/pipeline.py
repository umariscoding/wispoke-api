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

from google.genai.types import EndSensitivity, StartSensitivity, ThinkingConfig
from pipecat.services.google.gemini_live.llm import GeminiVADParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.utils import create_stream_resampler, mix_audio
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    LLMContextFrame,
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
            f"Book a NEW appointment. ONLY call AFTER collecting {field_labels}, "
            "date, time, AND confirmation. NEVER use placeholder data."
        ),
        properties=properties,
        required=required,
    )


def _reschedule_appointment_schema() -> FunctionSchema:
    return FunctionSchema(
        name="reschedule_appointment",
        description=(
            "Move an existing appointment to a new date/time. Call ONLY when "
            "the caller explicitly asks to reschedule, has confirmed their "
            "phone number, and has confirmed the new date+time."
        ),
        properties={
            "caller_phone": {"type": "string", "description": "Phone number of the caller (used to look up their appointment)"},
            "new_scheduled_date": {"type": "string", "description": "New date in YYYY-MM-DD"},
            "new_start_time": {"type": "string", "description": "New start time in HH:MM 24-hour"},
        },
        required=["caller_phone", "new_scheduled_date", "new_start_time"],
    )


def _cancel_appointment_schema() -> FunctionSchema:
    return FunctionSchema(
        name="cancel_appointment",
        description=(
            "Cancel an existing appointment. Call ONLY when the caller "
            "explicitly asks to cancel and has confirmed their phone number."
        ),
        properties={
            "caller_phone": {"type": "string", "description": "Phone number of the caller (used to look up their appointment)"},
        },
        required=["caller_phone"],
    )


def _lookup_appointments_schema() -> FunctionSchema:
    return FunctionSchema(
        name="lookup_my_appointments",
        description=(
            "Look up the caller's upcoming appointments by phone number. Use "
            "when caller asks 'do I have an appointment?' or 'when is my "
            "appointment?'. The phone number must be confirmed first."
        ),
        properties={
            "caller_phone": {"type": "string", "description": "Phone number to look up"},
        },
        required=["caller_phone"],
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


_DIGIT_WORDS = {
    "zero": "0", "oh": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def _sanitize_phone(raw: Optional[str]) -> Optional[str]:
    """Normalize a dictated phone number to digits (+ optional leading +).

    Handles three classes of artifacts native-audio Gemini commonly leaves:
      - English digit words: "five seven nine" → "579"
      - Repeat shorthand: "double eight" → "88", "triple two" → "222"
        (also "treble" — UK English)
      - Noise tokens: spaces, dashes, parens, the word "plus"

    Order matters: words → digits FIRST (so "double eight" becomes "double 8"),
    THEN expand "double X" / "triple X" into the repeated digit, THEN strip
    everything that isn't a digit or leading +.
    """
    if not raw:
        return raw
    import re

    s = " " + raw.lower().strip() + " "

    # Common spoken plus-sign before a country code.
    s = s.replace(" plus ", " + ")

    # Words → digits. Word-boundary matching avoids butchering "twenty".
    word_re = re.compile(r"\b(" + "|".join(_DIGIT_WORDS) + r")\b")
    s = word_re.sub(lambda m: _DIGIT_WORDS[m.group(0)], s)

    # "double 5" → "55", "triple 7" → "777". Run after word→digit so the
    # right-hand side is guaranteed to be a single digit.
    s = re.sub(r"\b(?:double|dbl)\s+(\d)", lambda m: m.group(1) * 2, s)
    s = re.sub(r"\b(?:triple|treble)\s+(\d)", lambda m: m.group(1) * 3, s)

    # Strip everything except digits and a single leading +.
    plus = "+" if "+" in s else ""
    digits = "".join(c for c in s if c.isdigit())
    out = (plus + digits) or None
    return out


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


def _suggest_alternatives(
    company_id: str,
    scheduled_date: str,
    requested_hhmm: str,
    duration_min: int,
) -> Optional[str]:
    """Return a verbatim "I have X or Y" phrase based on the 2 currently-open
    slots nearest to the requested time. Empty string if nothing's left
    today; let the caller fall back to "want to try a different day?"."""
    try:
        from app.features.availability.service import get_available_slots_for_date
        slots = get_available_slots_for_date(company_id, scheduled_date, duration_min) or []
    except Exception:
        return None
    if not slots:
        return None

    try:
        target = datetime.strptime(requested_hhmm, "%H:%M")
    except ValueError:
        return None

    def _dist(slot):
        s = datetime.strptime(slot["start_time"][:5], "%H:%M")
        return abs((s - target).total_seconds())

    nearest = sorted(slots, key=_dist)[:2]
    spoken = [_spoken_time(s["start_time"][:5]) for s in nearest]
    if len(spoken) == 1:
        return f"I have {spoken[0]} open instead — want it?"
    return f"I have {spoken[0]} or {spoken[1]} open — either work?"


def _coerce_hhmm(raw: Optional[str]) -> Optional[str]:
    """Normalize an LLM-provided time string to strict HH:MM 24-hour form.

    Native-audio Gemini occasionally hands the tool "4:30 PM" or "16:30:00"
    instead of the schema-required "16:30". Coerce common variants here so a
    booking attempt isn't lost to a format quirk."""
    if not raw:
        return None
    s = raw.strip().upper()
    # "16:30" / "16:30:00" / "9:00"
    import re
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?$", s)
    if not m:
        return None
    h, mm, period = int(m.group(1)), int(m.group(2)), m.group(3)
    if period == "PM" and h < 12:
        h += 12
    elif period == "AM" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= mm < 60):
        return None
    return f"{h:02d}:{mm:02d}"


def _make_book_handler(
    company_id: str,
    va_settings: Dict[str, Any],
    on_booked: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
    tool_log: Optional[List[Dict[str, Any]]] = None,
):
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)
        logger.info("book_appointment called for %s with args=%s", company_id, args)
        if tool_log is not None:
            tool_log.append({"call": "book_appointment", "args": dict(args), "ts": time.monotonic()})

        if "caller_email" in args:
            args["caller_email"] = _sanitize_email(args.get("caller_email"))
        if "caller_phone" in args:
            args["caller_phone"] = _sanitize_phone(args.get("caller_phone"))

        # Normalize time format BEFORE the missing-args check so "4:30 PM"
        # doesn't get bounced as a format error after the LLM nailed everything
        # else right.
        coerced_time = _coerce_hhmm(args.get("start_time"))
        if coerced_time:
            args["start_time"] = coerced_time

        async def _fail(reason: str, say: str) -> None:
            logger.warning("book_appointment failed for %s: %s", company_id, reason)
            if tool_log is not None:
                tool_log.append({"call": "book_appointment", "result": "failure", "reason": reason})

            # Loop prevention: if this is the 3rd+ consecutive booking failure,
            # stop trying and offer to take a callback. Real receptionists know
            # when the system is fighting them and pivot — the agent should too.
            failure_streak = 0
            if tool_log is not None:
                for entry in reversed(tool_log):
                    if entry.get("call") == "book_appointment" and entry.get("result") == "failure":
                        failure_streak += 1
                    elif entry.get("call") == "book_appointment" and entry.get("result") == "success":
                        break
            if failure_streak >= 3:
                say = (
                    "Hmm, I'm having trouble getting this booked right now. "
                    "Want me to take your name and number and have someone call you back to confirm?"
                )

            # Force verbatim relay — softer "tell the caller what went wrong"
            # phrasings collapsed into "ran into an issue" hallucinations.
            await params.result_callback(
                {
                    "success": False,
                    "reason": reason,
                    "message": f'Say EXACTLY: "{say}"',
                }
            )

        # Validate every required field per the tenant's configuration, with
        # a friendly ask for the specific missing piece — so a partial tool call
        # (Gemini occasionally drops one arg) recovers in one turn instead of
        # restarting the whole booking flow.
        configured_fields = va_settings.get("appointment_fields") or ["name", "phone"]
        _MISSING_PROMPTS = {
            "scheduled_date": "Sorry, what day did you want?",
            "start_time": "Sorry, what time did you want?",
            "caller_name": "Sorry, what's your name?",
            "caller_phone": "Sorry, what's your phone number?",
            "caller_email": "Sorry, what's your email?",
            "caller_address": "Sorry, what's the address?",
        }
        required_args = ["scheduled_date", "start_time"]
        for f in configured_fields:
            fd = FIELD_DEFS.get(f)
            if fd:
                required_args.append(fd["param"])

        for arg_name in required_args:
            if not args.get(arg_name):
                await _fail(
                    f"missing {arg_name}",
                    _MISSING_PROMPTS.get(arg_name, f"Sorry, can you give me your {arg_name.replace('caller_', '').replace('_', ' ')}?"),
                )
                return

        date_err = _validate_booking_date(args["scheduled_date"])
        if date_err:
            await _fail(
                date_err,
                f"Sorry, that date doesn't look right — today is {datetime.now(timezone.utc).strftime('%A, %B %d')}. "
                "Which day did you actually want?",
            )
            return

        from app.features.appointments.service import create_appointment

        duration = va_settings.get("appointment_duration_min", 30)
        try:
            start = datetime.strptime(args["start_time"], "%H:%M")
        except ValueError:
            await _fail(
                f"start_time must be HH:MM (got {args.get('start_time')!r})",
                "Sorry, I missed that time — could you say it again?",
            )
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
            # Translate common backend errors into caller-friendly verbatim
            # phrases. The model relays these literally. For slot conflicts we
            # offer the two nearest still-open slots so the caller doesn't have
            # to start the whole "what times do you have" dance over.
            spoken_t = _spoken_time(args["start_time"])
            spoken_d = _spoken_date(args["scheduled_date"])
            slot_problem = "is not an offered slot" in reason or "conflicts with existing appointment" in reason

            if slot_problem:
                alt_phrase = _suggest_alternatives(
                    company_id, args["scheduled_date"], args["start_time"], duration
                )
                if alt_phrase:
                    say = f"Sorry, {spoken_t} on {spoken_d} isn't open. {alt_phrase}"
                else:
                    say = f"Sorry, {spoken_t} on {spoken_d} isn't open. Want to try a different day?"
            else:
                say = f"Sorry, I couldn't book that — {reason}. Want to try a different time?"
            await _fail(reason, say)
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

        if tool_log is not None:
            tool_log.append({"call": "book_appointment", "result": "success", "appointment_id": result.get("appointment_id")})
        logger.info("book_appointment succeeded for %s: appointment_id=%s", company_id, result.get("appointment_id"))

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


def _make_reschedule_handler(
    company_id: str,
    va_settings: Dict[str, Any],
    tool_log: Optional[List[Dict[str, Any]]] = None,
):
    """Move an existing appointment for caller_phone to a new date/time.

    Lookup is by phone number, not appointment_id — the caller doesn't know
    that. If the phone matches multiple upcoming appointments we move the
    earliest one (most likely the one they're calling about).
    """
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)
        logger.info("reschedule_appointment called for %s with args=%s", company_id, args)
        if tool_log is not None:
            tool_log.append({"call": "reschedule_appointment", "args": dict(args), "ts": time.monotonic()})

        phone = _sanitize_phone(args.get("caller_phone"))
        new_date = args.get("new_scheduled_date")
        new_time = _coerce_hhmm(args.get("new_start_time"))

        async def _fail(reason: str, say: str) -> None:
            logger.warning("reschedule_appointment failed for %s: %s", company_id, reason)
            if tool_log is not None:
                tool_log.append({"call": "reschedule_appointment", "result": "failure", "reason": reason})
            await params.result_callback({"success": False, "reason": reason, "message": f'Say EXACTLY: "{say}"'})

        if not phone:
            await _fail("missing caller_phone", "Sorry, what's the phone number on the appointment?")
            return
        if not new_date or not new_time:
            await _fail("missing new date/time", "Sorry, what new day and time did you want?")
            return

        from app.features.appointments import repository as appt_repo
        from app.features.appointments.service import update_appointment, create_appointment

        existing_list = appt_repo.get_upcoming_by_phone(company_id, phone)
        if not existing_list:
            await _fail(
                "no upcoming appointment for that phone",
                "Hmm, I don't see an upcoming appointment under that number. Want to book a new one?",
            )
            return
        existing = existing_list[0]

        date_err = _validate_booking_date(new_date)
        if date_err:
            await _fail(date_err, "Sorry, that new date doesn't look right. Which day did you want?")
            return

        # Strategy: cancel the old, create the new (with the same caller info).
        # This way the create_appointment validation (offered slot, no conflict)
        # runs naturally for the new slot.
        duration = va_settings.get("appointment_duration_min", 30)
        try:
            start = datetime.strptime(new_time, "%H:%M")
        except ValueError:
            await _fail(f"new_start_time must be HH:MM (got {new_time!r})", "Sorry, I missed that time — could you say it again?")
            return

        try:
            new_appt = create_appointment(company_id, {
                "caller_name": existing.get("caller_name"),
                "caller_phone": existing.get("caller_phone"),
                "caller_email": existing.get("caller_email"),
                "scheduled_date": new_date,
                "start_time": new_time,
                "end_time": (start + timedelta(minutes=duration)).strftime("%H:%M"),
                "duration_min": duration,
                "service_type": existing.get("service_type"),
                "notes": existing.get("notes"),
                "source": "voice_agent",
            })
        except Exception as e:
            reason = str(e) or "unknown error"
            spoken_t = _spoken_time(new_time)
            spoken_d = _spoken_date(new_date)
            if "is not an offered slot" in reason or "conflicts with existing appointment" in reason:
                alt = _suggest_alternatives(company_id, new_date, new_time, duration)
                say = f"Sorry, {spoken_t} on {spoken_d} isn't open. {alt}" if alt else f"Sorry, {spoken_t} on {spoken_d} isn't open. Want a different day?"
            else:
                say = f"Sorry, I couldn't reschedule — {reason}."
            await _fail(reason, say)
            return

        try:
            update_appointment(company_id, existing["appointment_id"], {"status": "cancelled"})
        except Exception:
            logger.exception("Failed to mark old appointment cancelled after reschedule")

        if tool_log is not None:
            tool_log.append({"call": "reschedule_appointment", "result": "success",
                             "old_id": existing["appointment_id"], "new_id": new_appt.get("appointment_id")})

        spoken_t = _spoken_time(new_time)
        spoken_d = _spoken_date(new_date)
        await params.result_callback({
            "success": True,
            "message": f'Say EXACTLY: "All moved — you\'re now on {spoken_d} at {spoken_t}. See you then!"',
        })

    return handler


def _make_cancel_handler(
    company_id: str,
    va_settings: Dict[str, Any],
    tool_log: Optional[List[Dict[str, Any]]] = None,
):
    """Cancel the caller's upcoming appointment by phone number."""
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)
        logger.info("cancel_appointment called for %s with args=%s", company_id, args)
        if tool_log is not None:
            tool_log.append({"call": "cancel_appointment", "args": dict(args), "ts": time.monotonic()})

        phone = _sanitize_phone(args.get("caller_phone"))

        async def _fail(reason: str, say: str) -> None:
            logger.warning("cancel_appointment failed for %s: %s", company_id, reason)
            if tool_log is not None:
                tool_log.append({"call": "cancel_appointment", "result": "failure", "reason": reason})
            await params.result_callback({"success": False, "reason": reason, "message": f'Say EXACTLY: "{say}"'})

        if not phone:
            await _fail("missing caller_phone", "Sorry, what's the phone number on the appointment?")
            return

        from app.features.appointments import repository as appt_repo
        from app.features.appointments.service import update_appointment

        existing_list = appt_repo.get_upcoming_by_phone(company_id, phone)
        if not existing_list:
            await _fail(
                "no upcoming appointment for that phone",
                "I don't see an upcoming appointment under that number — nothing to cancel.",
            )
            return
        existing = existing_list[0]

        try:
            update_appointment(company_id, existing["appointment_id"], {"status": "cancelled"})
        except Exception as e:
            reason = str(e) or "unknown error"
            await _fail(reason, "Sorry, I couldn't cancel that just now — something went wrong.")
            return

        if tool_log is not None:
            tool_log.append({"call": "cancel_appointment", "result": "success", "appointment_id": existing["appointment_id"]})

        spoken_t = _spoken_time(existing["start_time"][:5])
        spoken_d = _spoken_date(existing["scheduled_date"])
        await params.result_callback({
            "success": True,
            "message": f'Say EXACTLY: "Done — your {spoken_d} at {spoken_t} appointment is cancelled. Take care!"',
        })

    return handler


def _make_lookup_handler(
    company_id: str,
    tool_log: Optional[List[Dict[str, Any]]] = None,
):
    """Read back the caller's upcoming appointments by phone."""
    async def handler(params: FunctionCallParams) -> None:
        args = dict(params.arguments)
        logger.info("lookup_my_appointments called for %s with args=%s", company_id, args)
        if tool_log is not None:
            tool_log.append({"call": "lookup_my_appointments", "args": dict(args), "ts": time.monotonic()})

        phone = _sanitize_phone(args.get("caller_phone"))
        if not phone:
            await params.result_callback({
                "success": False,
                "message": 'Say EXACTLY: "Sorry, what number should I look up?"',
            })
            return

        from app.features.appointments import repository as appt_repo
        appts = appt_repo.get_upcoming_by_phone(company_id, phone)

        if tool_log is not None:
            tool_log.append({"call": "lookup_my_appointments", "result": "success", "count": len(appts)})

        if not appts:
            say = "I don't see any upcoming appointments under that number."
        elif len(appts) == 1:
            a = appts[0]
            say = f"You have one — {_spoken_date(a['scheduled_date'])} at {_spoken_time(a['start_time'][:5])}."
        else:
            parts = [f"{_spoken_date(a['scheduled_date'])} at {_spoken_time(a['start_time'][:5])}" for a in appts[:3]]
            say = f"You have {len(appts)}: " + ", ".join(parts) + "."

        await params.result_callback({
            "success": True,
            "message": f'Say EXACTLY: "{say}"',
        })

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
# so a stale/typo'd setting can't crash the pipeline. The 09-2025 preview was
# removed from Google's pricing page (Dec 2025) and is treated as deprecated;
# saved settings still pointing at it fall back to DEFAULT silently.
SUPPORTED_GEMINI_LIVE_MODELS = {
    "gemini-2.5-flash-native-audio-preview-12-2025",  # Recommended (default)
    "gemini-3.1-flash-live-preview",                  # Newest preview, lowest latency
}

# Sentinel placed in the seeded "user" message that triggers the opening
# greeting. Filtered out before transcripts get persisted/displayed.
_GREETING_TRIGGER = "[SYSTEM:CALL_STARTED — greet the caller now]"

# NOTE on input transcription language: the Gemini Live API does NOT currently
# support `language_codes` on `AudioTranscriptionConfig`, even though the field
# exists in google-genai's Pydantic model — passing it makes `_connect` raise
# "language_codes parameter is not supported in Gemini API" and the session
# never starts. So we can't force English transcription server-side. We rely
# on (1) `language="en-US"` in Settings (pins speech-output language and may
# influence transcription) and (2) a "respond only in English" directive in
# the system prompt. Re-introduce a transcription-language config only after
# verifying Google has shipped the feature in `_live_converters.py`.


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
    tool_log: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[PipelineTask, LLMContext]:
    """Single-service pipeline using Gemini Live's native speech-to-speech.

    Silero VAD feeds the user-side context aggregator; Gemini's own server-side
    turn detection drives end-of-turn signaling.
    """
    gemini_key = app_settings.gemini_api_key
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    tools = ToolsSchema(standard_tools=[
        _book_appointment_schema(va_settings),
        _reschedule_appointment_schema(),
        _cancel_appointment_schema(),
        _lookup_appointments_schema(),
    ])

    system_prompt = build_system_prompt(company_id, va_settings)
    greeting = (va_settings.get("greeting_message") or "").strip() or (
        "Hello! Thanks for calling. How can I help you today?"
    )
    full_prompt = (
        f"{system_prompt}\n\n# First Words\n"
        f'Begin the call by saying exactly: "{greeting}"'
    )

    # Latency-tuned settings — values lifted directly from Google's documented
    # low-latency example at ai.google.dev/gemini-api/docs/live-api/capabilities:
    #
    #   - silence_duration_ms=100, prefix_padding_ms=20: Google's own example.
    #     Docs: "The larger silence_duration_ms... will increase the model's
    #     latency." → smaller is faster.
    #   - start/end_sensitivity=LOW: matches Google's low-latency example.
    #     HIGH "ends speech more often" (more aggressive cutoffs) but the
    #     example explicitly uses LOW for the canonical config.
    #   - thinking_budget=0: docs say "Disable thinking by setting
    #     thinkingBudget = 0" — fastest TTFT possible. The "Today is..." anchor
    #     in the prompt + the server-side _validate_booking_date catch the
    #     date-arithmetic class of errors that originally pushed us off 0.
    #   - max_tokens=200: caps long monologues. Doesn't affect TTFT.
    #   - language="en-US": pins speech-output language. (Input transcription
    #     language hint is not supported by the Live API as of late 2026.)
    model = _resolve_model(va_settings)
    llm = GeminiLiveLLMService(
        api_key=gemini_key,
        settings=GeminiLiveLLMService.Settings(
            model=model,
            voice=_resolve_gemini_voice(va_settings.get("voice_model")),
            language="en-US",
            system_instruction=full_prompt,
            max_tokens=200,
            thinking=ThinkingConfig(thinking_budget=0),
            vad=GeminiVADParams(
                start_sensitivity=StartSensitivity.START_SENSITIVITY_LOW,
                end_sensitivity=EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=20,
                silence_duration_ms=100,
            ),
        ),
    )
    logger.info("voice_agent: using Gemini Live model=%s", model)
    llm.register_function(
        "book_appointment",
        _make_book_handler(company_id, va_settings, on_booked, tool_log=tool_log),
    )
    llm.register_function(
        "reschedule_appointment",
        _make_reschedule_handler(company_id, va_settings, tool_log=tool_log),
    )
    llm.register_function(
        "cancel_appointment",
        _make_cancel_handler(company_id, va_settings, tool_log=tool_log),
    )
    llm.register_function(
        "lookup_my_appointments",
        _make_lookup_handler(company_id, tool_log=tool_log),
    )

    # Seed a single user message that triggers Gemini's first turn. Without
    # this, _create_initial_response sees an empty messages list and returns
    # without producing the greeting, so the bot stays silent until the user
    # speaks. We filter the seed back out at transcript-serialization time.
    context = LLMContext(
        messages=[{"role": "user", "content": _GREETING_TRIGGER}],
        tools=tools,
    )
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
        # Filter out the synthetic greeting trigger (see _GREETING_TRIGGER).
        if text.strip() == _GREETING_TRIGGER:
            continue
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

    # Gemini Live doesn't populate `message.tool_calls` on context messages,
    # so the standard transcript serializer never sees booking attempts. The
    # handler appends to this list and we splice the entries into the saved
    # transcript at end-of-call so we can debug what was actually attempted.
    tool_log: List[Dict[str, Any]] = []

    task, context = _build_gemini_task(
        company_id,
        va_settings,
        transport,
        audio_in_sample_rate=audio_in_sample_rate,
        audio_out_sample_rate=audio_out_sample_rate,
        on_booked=on_booked,
        extra_processors=[recorder],
        tool_log=tool_log,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_t, _c):
        t0_holder["t"] = time.monotonic()
        logger.info("voice_agent recording: call %s started", call_log_id)
        # Push the seeded context into the LLM. GeminiLiveLLMService routes
        # LLMContextFrame → _handle_context → _create_initial_response, which
        # sends the seeded "[SYSTEM:CALL_STARTED]" message to Gemini and
        # triggers the greeting per the system_instruction. Without a context
        # frame, Gemini stays silent until the user speaks first.
        await task.queue_frames([LLMContextFrame(context=context)])

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

            # Splice tool-call entries into the message transcript so the saved
            # call_log shows what the model attempted and what came back.
            tool_entries: List[Dict[str, Any]] = []
            for entry in tool_log:
                t0 = t0_holder.get("t")
                ts = round(max(0.0, entry["ts"] - t0), 2) if (t0 and "ts" in entry) else None
                if "args" in entry:
                    txt = f"{entry['call']}({entry['args']})"
                elif entry.get("result") == "success":
                    txt = f"{entry['call']} → success (appointment_id={entry.get('appointment_id')})"
                else:
                    txt = f"{entry['call']} → failure: {entry.get('reason', 'unknown')}"
                row = {"role": "tool_call", "content": txt}
                if ts is not None:
                    row["t"] = ts
                tool_entries.append(row)

            transcript = _attach_timestamps(
                _serialize_transcript(list(context.messages)),
                turn_events,
            )
            # Append tool-call entries to the end (cheap, debug-only — they
            # don't disrupt the chat-style display the FE renders).
            transcript.extend(tool_entries)
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

    # Hard cap on call duration. If a browser tab closes without a clean
    # WebRTC teardown, the peer connection can linger and Gemini Live keeps
    # the WebSocket open — burning quota for nothing. 5 min covers a normal
    # appointment-booking call with margin (real calls are ~1-2 min).
    import asyncio
    MAX_CALL_DURATION_SECS = 5 * 60

    async def _watchdog():
        await asyncio.sleep(MAX_CALL_DURATION_SECS)
        logger.warning(
            "voice_agent: call %s exceeded %ds cap — cancelling task",
            call_log_id, MAX_CALL_DURATION_SECS,
        )
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    watchdog_task = asyncio.create_task(_watchdog())
    try:
        await runner.run(task)
    finally:
        watchdog_task.cancel()


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
