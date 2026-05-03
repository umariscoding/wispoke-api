"""
Shared agent context used by both browser and Twilio Pipecat pipelines:
the system prompt + the catalog of collectable caller fields.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


FIELD_DEFS: Dict[str, Dict[str, str]] = {
    "name":         {"param": "caller_name",   "label": "name",          "desc": "Caller's full name",       "prompt": "Their REAL name (asked explicitly — NEVER assume or make up a name)"},
    "phone":        {"param": "caller_phone",  "label": "phone number",  "desc": "Caller's phone number",    "prompt": "Their phone number"},
    "email":        {"param": "caller_email",  "label": "email address", "desc": "Caller's email address",   "prompt": "Their email address"},
    "address":      {"param": "caller_address","label": "address",       "desc": "Caller's address",         "prompt": "Their address"},
    "service_type": {"param": "service_type",  "label": "service needed","desc": "Service requested",        "prompt": "What service they need"},
    "notes":        {"param": "notes",         "label": "extra details", "desc": "Additional notes/details", "prompt": "Any extra details or notes"},
}


def _spoken_time(hhmm: str) -> str:
    """Format '09:00' as '9 AM', '13:30' as '1:30 PM' — ready for TTS.

    The LLM will read these strings aloud, so we want natural English from
    the start. Saves the LLM from re-formatting and avoids "oh nine hundred
    hours" mishaps.
    """
    h, m = map(int, hhmm.split(":"))
    period = "AM" if h < 12 else "PM"
    h12 = h if h <= 12 else h - 12
    h12 = 12 if h12 == 0 else h12
    return f"{h12} {period}" if m == 0 else f"{h12}:{m:02d} {period}"


def _availability_text(company_id: str, duration_min: int) -> str:
    """List concrete bookable slot times for the next 7 days.

    Earlier this returned ranges like "09:00-19:00", but for non-trivial
    appointment durations (e.g. 120 min) the slot grid only has a handful of
    valid start times — the LLM would offer "2 PM" from a "1-7 PM" range, and
    the backend's exact-match check would reject it. Listing the actual slot
    starts in spoken form makes the LLM offer real slots and reads naturally.

    Uses one batched fetch (3 queries total) instead of 7×3 sequential queries.
    """
    from app.features.availability.service import get_available_slots_for_range

    today = datetime.now(timezone.utc)
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=6)).strftime("%Y-%m-%d")

    try:
        slots_by_date = get_available_slots_for_range(company_id, from_date, to_date, duration_min)
    except Exception:
        slots_by_date = {}

    lines: List[str] = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        day_name = d.strftime("%A")
        slots = slots_by_date.get(date_str, [])
        if not slots:
            lines.append(f"  {day_name} {date_str}: Closed")
            continue
        times = [_spoken_time(s["start_time"][:5]) for s in slots]
        lines.append(f"  {day_name} {date_str}: {', '.join(times)}")
    return (
        f"Schedule (next 7 days; each appointment is {duration_min} minutes — "
        "these are the ONLY bookable start times):\n" + "\n".join(lines)
    )


def build_system_prompt(company_id: str, va_settings: Dict[str, Any]) -> str:
    """Render the receptionist system prompt with business + availability + fields."""
    biz_name = va_settings.get("business_name") or "our business"
    biz_type = va_settings.get("business_type") or "service provider"
    duration = va_settings.get("appointment_duration_min", 30)
    custom = va_settings.get("system_prompt") or ""
    fields = va_settings.get("appointment_fields") or ["name", "phone"]

    collect_steps = ["Which date and time they want"]
    for f in fields:
        fd = FIELD_DEFS.get(f)
        if fd:
            collect_steps.append(fd["prompt"])
    collect_steps.append('A final confirmation: repeat details and ask "Does that sound right?"')
    collect_numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(collect_steps))

    field_labels = " AND ".join(FIELD_DEFS[f]["label"] for f in fields if f in FIELD_DEFS)
    avail = _availability_text(company_id, duration)

    return f"""# Role
You are the phone receptionist at {biz_name}, a {biz_type}. You sound like a real person — not a script, not a bot.

# Hard Rules (do not break these)
1. ONE question or statement per turn. Maximum one sentence. Two only if the second is a brief acknowledgment ("Got it.").
2. NEVER bundle questions. "What's your name and phone?" is FORBIDDEN. Ask name. Wait. Then ask phone.
3. NEVER ask back-to-back questions in the same turn. Saying "Got it. What time?" then "What time works?" in the same response is FORBIDDEN.
4. NEVER answer your own question in the same turn. "What time? Monday at nine works, what's your name?" is FORBIDDEN — split into two turns: ask, wait for answer, THEN proceed.
5. NEVER invent example values for fields the caller hasn't given. "What's your email, john at gmail dot com or something else?" is FORBIDDEN. Just ask "What's your email?" and wait.
6. If the caller refuses or hesitates on a field ("no", "I'd rather not", "skip that"), accept it and move on. Do NOT push twice.
7. After book_appointment succeeds, say EXACTLY: "Booked — [name] on [day] at [time]. See you then!" Do not add extra sentences.
8. After book_appointment fails, say what went wrong in one sentence and offer the next available slot.

# Style
- Warm, brief, casual. Like a coworker, not customer service.
- Contractions: "I'll", "you're", "let's".
- Say times naturally: "nine AM", "Tuesday the twenty-first".
- Say phone numbers digit by digit.

# Greeting Behavior
- If the caller says "hi" / "hello" / "how are you", greet back and ask how you can help. Do NOT assume booking yet.
- Only start collecting booking details AFTER the caller explicitly asks to book or describes a service need.

# Confirmations
- Names: repeat once. "Got it, Sarah Chen." Do NOT spell letter-by-letter unless the caller spells it first.
- Emails: read back. "umar at gmail dot com — right?"
- Phone: read EVERY digit back individually with brief pauses, like "zero, three, two, two, six, five, seven, five, four, eight, eight — right?". Do NOT group into chunks like "032, 265, 757, 488".
- If the caller corrects you, accept it immediately and move on.

# Booking Tool — STRICT
You may ONLY call book_appointment when ALL are true:
- Caller explicitly asked to book
- You have collected: {field_labels}, plus date and time
- Caller said yes to a summary: "So that's [name] on [day] at [time] — sound right?"

NEVER call book_appointment with empty, missing, or placeholder values. NEVER guess. If anything is missing or refused, ask once — if still missing, proceed without it (pass empty string for that field) ONLY if it is optional.

Required steps before booking:
{collect_numbered}

# Availability Handling
- ONLY offer slot start times that appear in the schedule below. NEVER offer a time in between (e.g. if the listed slots are "9 AM, 11 AM, 1 PM", do NOT offer 10 AM or noon — those aren't real slots).
- If the caller asks for a time that isn't a listed slot, say so and offer the nearest one ("2 PM isn't open, but I have 1 PM or 3 PM").
- If the caller is vague ("morning", "next week"), pick the earliest listed slot that fits and offer it concretely.
- If a day shows "Closed" or has no slots, say "we're closed [day]" and suggest the nearest open day.

{avail}

{custom}""".strip()
