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


def _availability_text(company_id: str, duration_min: int) -> str:
    """Summarize the next 7 days of availability for the system prompt."""
    from app.features.availability.service import get_available_slots_for_date

    today = datetime.now(timezone.utc)
    lines: List[str] = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        day_name = d.strftime("%A")
        try:
            slots = get_available_slots_for_date(company_id, date_str, duration_min)
            if not slots:
                lines.append(f"  {day_name} {date_str}: Closed")
                continue
            ranges, rs, re_ = [], slots[0]["start_time"], slots[0]["end_time"]
            for s in slots[1:]:
                if s["start_time"] == re_:
                    re_ = s["end_time"]
                else:
                    ranges.append(f"{rs}-{re_}")
                    rs, re_ = s["start_time"], s["end_time"]
            ranges.append(f"{rs}-{re_}")
            lines.append(f"  {day_name} {date_str}: {', '.join(ranges)}")
        except Exception:
            lines.append(f"  {day_name} {date_str}: Closed")
    return "Schedule (next 7 days):\n" + "\n".join(lines)


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
