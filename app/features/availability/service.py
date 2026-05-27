"""
Availability — business logic.
"""

from typing import Dict, Any, List, Optional

from app.core.exceptions import NotFoundError, ValidationError
from app.features.availability import repository as repo


DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def get_weekly_schedule(company_id: str) -> List[Dict[str, Any]]:
    return repo.get_schedules(company_id)


# Postgres CHECK constraint requires `end_time > start_time`, so we use
# 23:59:59 — covers the full day for booking purposes (slot duration is
# always ≥ 5 minutes so 23:59 → 24:00 round-trip can't be selected).
_FULL_DAY_START = "00:00:00"
_FULL_DAY_END = "23:59:59"


def seed_default_availability(company_id: str) -> List[Dict[str, Any]]:
    """Insert a 24/7 default schedule for a fresh tenant.

    Idempotent: if the tenant already has any active schedule rows, this is a
    no-op so we don't double-insert on retry. Returns the rows that exist
    after the call (either the freshly inserted set or what was already there).

    Called from the auth registration flow. Best-effort by the caller — a
    failure here should not break user signup; the dashboard's availability
    page lets them set it manually if needed.
    """
    existing = repo.get_schedules(company_id)
    if existing:
        return existing

    rows: List[Dict[str, Any]] = []
    for day_of_week in range(7):  # 0=Sunday … 6=Saturday
        row = repo.create_schedule_slot(
            company_id=company_id,
            day_of_week=day_of_week,
            start_time=_FULL_DAY_START,
            end_time=_FULL_DAY_END,
            is_active=True,
        )
        rows.append(row)
    return rows


def set_weekly_schedule(company_id: str, slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace the entire weekly schedule."""
    for slot in slots:
        if slot["start_time"] >= slot["end_time"]:
            raise ValidationError(f"start_time must be before end_time for {DAY_NAMES[slot['day_of_week']]}")

    repo.delete_schedules_for_company(company_id)

    created = []
    for slot in slots:
        row = repo.create_schedule_slot(
            company_id=company_id,
            day_of_week=slot["day_of_week"],
            start_time=slot["start_time"],
            end_time=slot["end_time"],
            is_active=slot.get("is_active", True),
        )
        created.append(row)
    return created


def get_exceptions(company_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None) -> List[Dict[str, Any]]:
    return repo.get_exceptions(company_id, from_date, to_date)


def create_exception(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return repo.create_exception(
        company_id=company_id,
        exception_date=data["exception_date"],
        is_available=data.get("is_available", False),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        reason=data.get("reason"),
    )


def delete_exception(company_id: str, exception_id: str) -> None:
    deleted = repo.delete_exception(exception_id, company_id)
    if not deleted:
        raise NotFoundError("Exception not found")


def _compute_slots(
    date_str: str,
    duration_min: int,
    schedules: List[Dict[str, Any]],
    day_exceptions: List[Dict[str, Any]],
    day_appointments: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Pure function: compute available slots from pre-fetched data."""
    from datetime import datetime, timedelta

    target = datetime.strptime(date_str, "%Y-%m-%d")
    day_of_week = (target.weekday() + 1) % 7  # Python: 0=Monday -> our 0=Sunday

    if any(not ex["is_available"] and ex.get("start_time") is None for ex in day_exceptions):
        return []

    day_slots = [s for s in schedules if s["day_of_week"] == day_of_week and s["is_active"]]

    for ex in day_exceptions:
        if ex["is_available"] and ex.get("start_time") and ex.get("end_time"):
            day_slots.append({"start_time": ex["start_time"], "end_time": ex["end_time"]})

    blocked_ranges = [
        (ex["start_time"], ex["end_time"])
        for ex in day_exceptions
        if not ex["is_available"] and ex.get("start_time") and ex.get("end_time")
    ]
    booked_ranges = [(a["start_time"], a["end_time"]) for a in day_appointments if a["status"] != "cancelled"]

    available = []
    for slot in day_slots:
        start = datetime.strptime(slot["start_time"][:5], "%H:%M")
        end = datetime.strptime(slot["end_time"][:5], "%H:%M")
        current = start

        while current + timedelta(minutes=duration_min) <= end:
            slot_start = current.strftime("%H:%M")
            slot_end = (current + timedelta(minutes=duration_min)).strftime("%H:%M")

            is_blocked = False
            for br_start, br_end in blocked_ranges + booked_ranges:
                if slot_start < br_end[:5] and slot_end > br_start[:5]:
                    is_blocked = True
                    break

            if not is_blocked:
                available.append({"start_time": slot_start, "end_time": slot_end})

            current += timedelta(minutes=duration_min)

    return available


def get_available_slots_for_date(company_id: str, date_str: str, duration_min: int = 30) -> List[Dict[str, str]]:
    """Get available time slots for a specific date, considering schedule + exceptions."""
    from app.features.appointments.repository import get_appointments_for_date

    schedules = repo.get_schedules(company_id)
    day_exceptions = repo.get_exceptions(company_id, date_str, date_str)
    day_appointments = get_appointments_for_date(company_id, date_str)
    return _compute_slots(date_str, duration_min, schedules, day_exceptions, day_appointments)


def get_available_slots_for_range(
    company_id: str, from_date: str, to_date: str, duration_min: int = 30
) -> Dict[str, List[Dict[str, str]]]:
    """Batch version: fetch schedule + exceptions + appointments once, compute slots per day.

    Replaces N×3 sequential queries with 3 total. Used by the voice agent prompt builder.
    """
    from datetime import datetime, timedelta
    from app.features.appointments.repository import get_appointments

    schedules = repo.get_schedules(company_id)
    exceptions = repo.get_exceptions(company_id, from_date, to_date)
    appointments = get_appointments(company_id, from_date, to_date)

    by_date_exc: Dict[str, List[Dict[str, Any]]] = {}
    for ex in exceptions:
        by_date_exc.setdefault(ex["exception_date"], []).append(ex)

    by_date_appt: Dict[str, List[Dict[str, Any]]] = {}
    for a in appointments:
        by_date_appt.setdefault(a["scheduled_date"], []).append(a)

    out: Dict[str, List[Dict[str, str]]] = {}
    cur = datetime.strptime(from_date, "%Y-%m-%d")
    end = datetime.strptime(to_date, "%Y-%m-%d")
    while cur <= end:
        d = cur.strftime("%Y-%m-%d")
        out[d] = _compute_slots(
            d, duration_min, schedules, by_date_exc.get(d, []), by_date_appt.get(d, [])
        )
        cur += timedelta(days=1)
    return out
