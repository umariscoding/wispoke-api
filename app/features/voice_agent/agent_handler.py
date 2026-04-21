"""
Voice Agent — Deepgram Agent API handler.

Proxies browser ↔ Deepgram Agent API, injects availability, handles booking.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import websockets

from app.core.config import settings as app_settings

logger = logging.getLogger("wispoke.voice.agent")

DEEPGRAM_AGENT_WS = "wss://agent.deepgram.com/v1/agent/converse"

_VOICE_MAP = {
    "aura-asteria-en": "aura-2-andromeda-en",
    "aura-luna-en": "aura-2-aurora-en",
    "aura-stella-en": "aura-2-andromeda-en",
    "aura-athena-en": "aura-2-aurora-en",
    "aura-hera-en": "aura-2-andromeda-en",
    "aura-orion-en": "aura-2-odysseus-en",
    "aura-arcas-en": "aura-2-atlas-en",
    "aura-perseus-en": "aura-2-odysseus-en",
    "aura-angus-en": "aura-2-atlas-en",
    "aura-orpheus-en": "aura-2-odysseus-en",
    "aura-helios-en": "aura-2-atlas-en",
    "aura-zeus-en": "aura-2-odysseus-en",
}


def _build_availability_text(company_id: str, duration_min: int = 30) -> str:
    """Summarize next 7 days as merged time ranges."""
    from app.features.availability.service import get_available_slots_for_date

    today = datetime.now(timezone.utc)
    lines = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        day_name = d.strftime("%A")
        try:
            slots = get_available_slots_for_date(company_id, date_str, duration_min)
            if not slots:
                lines.append(f"  {day_name} {date_str}: Closed")
                continue
            ranges, rs, re = [], slots[0]["start_time"], slots[0]["end_time"]
            for s in slots[1:]:
                if s["start_time"] == re:
                    re = s["end_time"]
                else:
                    ranges.append(f"{rs}-{re}")
                    rs, re = s["start_time"], s["end_time"]
            ranges.append(f"{rs}-{re}")
            lines.append(f"  {day_name} {date_str}: {', '.join(ranges)}")
        except Exception:
            lines.append(f"  {day_name} {date_str}: Closed")
    return "Schedule (next 7 days):\n" + "\n".join(lines)


FIELD_DEFS = {
    "name":         {"param": "caller_name",  "label": "name",          "desc": "Caller's full name",      "prompt": "Their REAL name (asked explicitly — NEVER assume or make up a name)"},
    "phone":        {"param": "caller_phone", "label": "phone number",  "desc": "Caller's phone number",   "prompt": "Their phone number"},
    "email":        {"param": "caller_email", "label": "email address", "desc": "Caller's email address",  "prompt": "Their email address"},
    "address":      {"param": "caller_address","label": "address",      "desc": "Caller's address",        "prompt": "Their address"},
    "service_type": {"param": "service_type", "label": "service needed","desc": "Service requested",       "prompt": "What service they need"},
    "notes":        {"param": "notes",        "label": "extra details", "desc": "Additional notes/details","prompt": "Any extra details or notes"},
}


def build_agent_config(company_id: str, va_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Build Deepgram Agent API settings with humanized prompt."""
    biz_name = va_settings.get("business_name") or "our business"
    biz_type = va_settings.get("business_type") or "service provider"
    duration = va_settings.get("appointment_duration_min", 30)
    custom = va_settings.get("system_prompt") or ""
    greeting = va_settings.get("greeting_message") or f"Hey! Thanks for calling {biz_name}. What can I help you with?"
    voice = _VOICE_MAP.get(va_settings.get("voice_model", ""), va_settings.get("voice_model") or "aura-2-odysseus-en")
    avail = _build_availability_text(company_id, duration)
    fields = va_settings.get("appointment_fields") or ["name", "phone"]

    # Build field collection rules
    collect_steps = ["Which date and time they want"]
    for f in fields:
        fd = FIELD_DEFS.get(f)
        if fd:
            collect_steps.append(fd["prompt"])
    collect_steps.append('A final confirmation: repeat details and ask "Does that sound right?"')
    collect_numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(collect_steps))

    field_labels = " AND ".join(FIELD_DEFS[f]["label"] for f in fields if f in FIELD_DEFS)

    prompt = f"""# Role
You are the friendly phone receptionist at {biz_name}, a {biz_type}. You sound like a real person, not a robot.

# Personality
- Warm, casual, helpful — like a favorite coworker
- Natural speech: "Sure thing!", "Let me check...", "Got it", "Oh perfect"
- Start sentences with "So", "Alright", "Well", "Okay so"

# Response Rules
- Keep responses to ONE or TWO short sentences
- No bullet points, lists, or markdown
- Say times naturally: "nine AM" not "09:00", "Tuesday the twenty-first" not "2026-04-21"
- Use conversational connectors: "Awesome", "Perfect", "Sounds good"
- If the caller asks for all available slots, tell them the full schedule for the week

# BOOKING RULES — EXTREMELY IMPORTANT
You MUST collect ALL of the following BEFORE calling book_appointment:
{collect_numbered}

NEVER call book_appointment until you have the caller's {field_labels} AND they have confirmed.
NEVER use placeholder data like "John Doe" — always ask explicitly.
If you don't have all the info, keep asking. Do NOT book.

# When Things Go Wrong
- Can't understand: "Sorry, didn't catch that — could you say that again?"
- Time taken: "Oh that one's booked. How about [next slot]?"
- Day full: "Hmm, [day] is pretty full. Want to try [next day]?"

{avail}

{custom}""".strip()

    # Build function parameters dynamically
    func_props = {
        "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD"},
        "start_time": {"type": "string", "description": "Start time in HH:MM"},
    }
    func_required = ["scheduled_date", "start_time"]

    for f in fields:
        fd = FIELD_DEFS.get(f)
        if fd:
            func_props[fd["param"]] = {"type": "string", "description": fd["desc"]}
            func_required.append(fd["param"])

    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 48000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
            "think": {
                "provider": {"type": "google", "model": "gemini-2.5-flash", "temperature": 0.8},
                "prompt": prompt,
                "functions": [{
                    "name": "book_appointment",
                    "description": f"Book an appointment. ONLY call AFTER collecting {field_labels}, date, time, AND confirmation. NEVER use placeholder data.",
                    "parameters": {"type": "object", "properties": func_props, "required": func_required},
                }],
            },
            "speak": {"provider": {"type": "deepgram", "model": voice}},
            "greeting": greeting,
        },
    }


async def handle_agent_ws(browser_ws, company_id: str, va_settings: Dict[str, Any]):
    """Proxy browser ↔ Deepgram Agent API with function call handling."""
    deepgram_key = app_settings.deepgram_api_key
    if not deepgram_key:
        await browser_ws.close(code=1011, reason="Server configuration error")
        return

    sample_rate = 48000
    try:
        init = await browser_ws.receive()
        if "text" in init:
            sample_rate = json.loads(init["text"]).get("sample_rate", 48000)
    except Exception:
        pass

    config = build_agent_config(company_id, va_settings)
    config["audio"]["input"]["sample_rate"] = sample_rate

    try:
        async with websockets.connect(DEEPGRAM_AGENT_WS, additional_headers={"Authorization": f"Token {deepgram_key}"}) as dg:
            await dg.send(json.dumps(config))
            await browser_ws.send_text(json.dumps({"type": "Ready"}))
            logger.info(f"Agent connected: company={company_id}")

            async def browser_to_dg():
                try:
                    while True:
                        data = await browser_ws.receive()
                        if data.get("type") == "websocket.disconnect":
                            break
                        if "bytes" in data:
                            await dg.send(data["bytes"])
                except Exception:
                    pass

            async def dg_to_browser():
                try:
                    async for msg in dg:
                        if isinstance(msg, bytes):
                            await browser_ws.send_bytes(msg)
                        else:
                            parsed = json.loads(msg)
                            if parsed.get("type") == "FunctionCallRequest":
                                await _handle_function_call(dg, browser_ws, company_id, va_settings, parsed)
                            else:
                                await browser_ws.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(browser_to_dg(), dg_to_browser())
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)


async def _handle_function_call(dg, browser_ws, company_id: str, va_settings: Dict[str, Any], msg: Dict[str, Any]):
    """Handle Deepgram function calls (book_appointment)."""
    for func in msg.get("functions", []):
        func_id, func_name = func.get("id", ""), func.get("name", "")
        try:
            args = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}

        logger.info(f"Function: {func_name} args={args}")

        if func_name == "book_appointment":
            try:
                if not args.get("scheduled_date") or not args.get("start_time") or not args.get("caller_name"):
                    raise ValueError("Missing required fields: caller_name, scheduled_date, start_time")
                from app.features.appointments.service import create_appointment
                duration = va_settings.get("appointment_duration_min", 30)
                start = datetime.strptime(args["start_time"], "%H:%M")
                result = create_appointment(company_id, {
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
                })
                content = {"success": True, "message": f"Booked {args.get('caller_name', 'caller')} on {args['scheduled_date']} at {args['start_time']}."}
                await browser_ws.send_text(json.dumps({"type": "AppointmentBooked", "appointment": result}))
            except Exception as e:
                logger.error(f"Booking failed: {e}")
                content = {"success": False, "message": f"Failed: {e}. Suggest another time."}
        else:
            content = {"success": False, "message": "Unknown function"}

        await dg.send(json.dumps({"type": "FunctionCallResponse", "id": func_id, "name": func_name, "content": json.dumps(content)}))
