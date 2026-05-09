"""
Agent context for the Gemini Live voice pipeline: the system prompt and
the catalog of collectable caller fields.
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


_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def spoken_time(hhmm: str) -> str:
    """Format '09:00' as '9 AM', '13:30' as '1:30 PM' — ready for TTS.

    The LLM will read these strings aloud, so we want natural English from
    the start. Saves the LLM from re-formatting and avoids "oh nine hundred
    hours" mishaps.
    """
    h, m = map(int, hhmm.split(":")[:2])
    period = "AM" if h < 12 else "PM"
    h12 = h if h <= 12 else h - 12
    h12 = 12 if h12 == 0 else h12
    return f"{h12} {period}" if m == 0 else f"{h12}:{m:02d} {period}"


# Internal alias kept for the existing call site in this module.
_spoken_time = spoken_time


def spoken_date(yyyy_mm_dd: str) -> str:
    """Format '2026-05-04' as 'Monday, May fourth' — natural for TTS.

    The booking confirmation reads this back to the caller, so we want the
    weekday + month + day. Keeps the day pronounceable (May fourth, not
    May four).
    """
    try:
        d = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d")
    except ValueError:
        return yyyy_mm_dd
    suffix = _ORDINAL_SUFFIX.get(d.day, "th")
    return f"{d.strftime('%A')}, {_MONTHS[d.month - 1]} {d.day}{suffix}"


def _availability_text(company_id: str, duration_min: int) -> str:
    """Render a compact next-7-days schedule for the system prompt.

    Format: "Wed May 13: open 9 AM – 4:30 PM" (one line per day, exception
    days enumerate the missing/taken slots). Listing every individual slot
    blew up to 100+ time strings and the model would lose track of half the
    day — saying "9 AM or 9:30 AM" when the full afternoon was open.
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
        short_day = d.strftime("%a")  # Mon, Tue, ...
        short_date = f"{_MONTHS[d.month - 1][:3]} {d.day}"  # May 13
        prefix = f"{short_day} {short_date}"

        slots = slots_by_date.get(date_str, [])
        if not slots:
            lines.append(f"- {prefix}: CLOSED")
            continue

        first_hhmm = slots[0]["start_time"][:5]
        last_hhmm = slots[-1]["start_time"][:5]
        first_spoken = _spoken_time(first_hhmm)
        last_spoken = _spoken_time(last_hhmm)

        # Compute the set of HH:MM strings that WOULD be present if every
        # slot from first to last were open. Diff against actual to find
        # the taken slots in the middle. Listing taken slots is shorter
        # than listing open slots when most of the day is free.
        actual_set = {s["start_time"][:5] for s in slots}
        expected = _slots_between(first_hhmm, last_hhmm, duration_min)
        taken_in_middle = [t for t in expected if t not in actual_set]

        if not taken_in_middle:
            lines.append(f"- {prefix}: open {first_spoken} – {last_spoken}")
        elif len(taken_in_middle) <= 4:
            taken_spoken = ", ".join(_spoken_time(t) for t in taken_in_middle)
            lines.append(f"- {prefix}: open {first_spoken} – {last_spoken} (taken: {taken_spoken})")
        else:
            # More than half the day is gone — list the OPEN slots instead.
            open_spoken = ", ".join(_spoken_time(s["start_time"][:5]) for s in slots)
            lines.append(f"- {prefix}: only {open_spoken}")

    return (
        f"# Schedule (next 7 days)\n"
        f"Each slot is {duration_min} minutes. Slots start every {duration_min} min.\n"
        + "\n".join(lines)
    )


def _slots_between(start_hhmm: str, end_hhmm: str, duration_min: int) -> List[str]:
    """Enumerate every duration_min slot from start_hhmm to end_hhmm, inclusive."""
    try:
        s = datetime.strptime(start_hhmm[:5], "%H:%M")
        e = datetime.strptime(end_hhmm[:5], "%H:%M")
    except ValueError:
        return []
    out: List[str] = []
    cur = s
    while cur <= e:
        out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=duration_min)
    return out


def build_system_prompt(company_id: str, va_settings: Dict[str, Any]) -> str:
    """Render the receptionist system prompt with business + availability + fields."""
    biz_name = va_settings.get("business_name") or "our business"
    biz_type = va_settings.get("business_type") or "service provider"
    duration = va_settings.get("appointment_duration_min", 30)
    custom = va_settings.get("system_prompt") or ""
    fields = va_settings.get("appointment_fields") or ["name", "phone"]

    # Field-by-field collection only — no separate "summary at the end" step.
    # Each field is read back inline as it's collected (see Confirmations
    # section), then book_appointment is called when all are gathered.
    collect_steps = ["Which date and time they want"]
    for f in fields:
        fd = FIELD_DEFS.get(f)
        if fd:
            collect_steps.append(fd["prompt"])
    collect_numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(collect_steps))

    field_labels = " AND ".join(FIELD_DEFS[f]["label"] for f in fields if f in FIELD_DEFS)
    avail = _availability_text(company_id, duration)

    # Anchor "today" at the top of the prompt. Without this, the model has
    # to infer relative dates ("tomorrow", "next Tuesday") from the bullet
    # list lower down — which is the #1 source of wrong-day bookings.
    now = datetime.now(timezone.utc)
    today_line = (
        f"Today is {now.strftime('%A')}, "
        f"{_MONTHS[now.month - 1]} {now.day}, {now.year} "
        f"({now.strftime('%Y-%m-%d')})."
    )

    return f"""You are the phone receptionist at {biz_name} ({biz_type}). You're a real person — mid-30s, friendly, efficient. You've done this for years and could do it in your sleep. Not chirpy, not formal, just normal.

# Today
{today_line}
Resolve relative dates ("tomorrow", "next Tuesday") against this date.

# Voice
- ENGLISH ONLY, regardless of caller's language.
- ONE short sentence per turn. ≤8 words ideally. Skip filler ("Sure!", "Of course!", "I'd be happy to").
- Contractions always ("I'll", "you're", "let's").
- Times spoken naturally ("nine AM", "Tuesday the thirteenth").
- Phone read-back: fast 3-4 digit groups ("oh-three-two-two, six-five-seven, five-four-eight-eight, right?").
- Email read-back: one breath ("umar-at-gmail-dot-com, right?").
- The moment the caller starts speaking, STOP. Don't finish your sentence over them. Let them talk.
- Don't apologize for things that aren't your fault. "Sorry" once if a slot's taken; not three times.

# What You Can Do
- **Book new** → `book_appointment`.
- **Reschedule** → `reschedule_appointment` (looks up by phone).
- **Cancel** → `cancel_appointment` (looks up by phone).
- **Check status** → `lookup_my_appointments` (looks up by phone).

Listen for intent:
- "Book / schedule / set up an appointment" → new.
- "Move / change my time / push back" → reschedule.
- "Cancel / I can't make it" → cancel.
- "Do I have / when is my appointment" → lookup.

# Closing the Call
When the caller signals they're done — "thanks", "that's all", "bye", "have a good day", "perfect", "okay great" with no follow-up question — close warmly in ONE short line ("Take care, see you then!" or "Sounds good, bye!"). Do NOT ask another question to extend the call. If they're already done, you're done.

# Edge Cases
- Ambiguous time ("around two-ish", "morning") → offer the nearest concrete slots ("2 PM or 2:30?").
- Caller says "let me check my calendar" or "hold on" → STAY SILENT until they speak again. Do not fill the silence.
- Half sentence ("I want to..." then pause) → wait. Don't guess what they were going to say.
- Background noise / no speech for 8+ seconds → "Still there?" once. If still nothing, "I'll let you go — call back when you're ready" and close.
- Caller speaks too fast / you missed it → "Sorry, one more time?" — never pretend you heard it.
- Caller says digits one at a time ("oh-three-two-two...") → wait until they pause naturally; don't read back per-digit, read back the whole number once they're done.

# Booking Flow (new appointments)
Steps in order:
{collect_numbered}

Read back each field in the same turn you collect it ("Got it, Omar."). If they correct you, accept and move on. If they refuse, skip it (only if optional).

# Availability
Use ONLY the schedule below. If a time isn't open, say so plainly and offer the nearest open slot ("4:15 isn't open, I have 4 PM or 4:30").

{avail}

# Tools
- `book_appointment`: call ONLY when you have {field_labels}, date, time — each read back without correction. Use `HH:MM` 24-hour ("16:30") for `start_time`, `YYYY-MM-DD` for `scheduled_date`. Never use placeholder values. NO recap before calling — inline read-backs are the confirmation.
- `reschedule_appointment`: needs `caller_phone` + new date + new time. The phone number identifies their existing appointment.
- `cancel_appointment`: needs `caller_phone`.
- `lookup_my_appointments`: needs `caller_phone`. Use to answer "do I have an appointment?" / "when is it?".

# Tool Results — Verbatim
The tool result includes a `message` field telling you EXACTLY what to say. Say it word-for-word. Don't paraphrase, don't add, don't shorten. The system has already chosen the right words for the caller.

{custom}""".strip()
