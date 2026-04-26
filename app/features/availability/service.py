"""
Availability — business logic.
"""

from typing import Dict, Any, List, Optional

from app.core.exceptions import NotFoundError, ValidationError
from app.features.availability import repository as repo


DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def get_weekly_schedule(company_id: str) -> List[Dict[str, Any]]:
    return repo.get_schedules(company_id)


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


def get_available_slots_for_date(company_id: str, date_str: str, duration_min: int = 30) -> List[Dict[str, str]]:
    """Get available time slots for a specific date, considering schedule + exceptions."""
    from datetime import datetime, timedelta

    target = datetime.strptime(date_str, "%Y-%m-%d")
    day_of_week = (target.weekday() + 1) % 7  # Python: 0=Monday -> our 0=Sunday

    # Check exceptions first
    exceptions = repo.get_exceptions(company_id, date_str, date_str)
    blocked_entirely = any(not ex["is_available"] and ex.get("start_time") is None for ex in exceptions)
    if blocked_entirely:
        return []

    # Get regular schedule for this day
    schedules = repo.get_schedules(company_id)
    day_slots = [s for s in schedules if s["day_of_week"] == day_of_week and s["is_active"]]

    # Add extra availability from exceptions
    for ex in exceptions:
        if ex["is_available"] and ex.get("start_time") and ex.get("end_time"):
            day_slots.append({"start_time": ex["start_time"], "end_time": ex["end_time"]})

    # Remove blocked time ranges from exceptions
    blocked_ranges = [
        (ex["start_time"], ex["end_time"])
        for ex in exceptions
        if not ex["is_available"] and ex.get("start_time") and ex.get("end_time")
    ]

    # Get existing appointments for this date
    from app.features.appointments.repository import get_appointments_for_date
    existing_appts = get_appointments_for_date(company_id, date_str)
    booked_ranges = [(a["start_time"], a["end_time"]) for a in existing_appts if a["status"] != "cancelled"]

    # Generate available slots
    available = []
    for slot in day_slots:
        start = datetime.strptime(slot["start_time"][:5], "%H:%M")
        end = datetime.strptime(slot["end_time"][:5], "%H:%M")
        current = start

        while current + timedelta(minutes=duration_min) <= end:
            slot_start = current.strftime("%H:%M")
            slot_end = (current + timedelta(minutes=duration_min)).strftime("%H:%M")

            # Check if slot overlaps with blocked ranges or booked appointments
            is_blocked = False
            for br_start, br_end in blocked_ranges + booked_ranges:
                br_s = br_start[:5]
                br_e = br_end[:5]
                if slot_start < br_e and slot_end > br_s:
                    is_blocked = True
                    break

            if not is_blocked:
                available.append({"start_time": slot_start, "end_time": slot_end})

            current += timedelta(minutes=duration_min)

    return available
