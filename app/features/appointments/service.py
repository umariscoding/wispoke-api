"""
Appointments — business logic.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from app.core.exceptions import NotFoundError, ValidationError
from app.features.appointments import repository as repo


def list_appointments(company_id: str, from_date: Optional[str] = None,
                      to_date: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    return repo.get_appointments(company_id, from_date, to_date, status)


def get_appointment(company_id: str, appointment_id: str) -> Dict[str, Any]:
    appt = repo.get_appointment_by_id(appointment_id, company_id)
    if not appt:
        raise NotFoundError("Appointment not found")
    return appt


def create_appointment(company_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if not data.get("scheduled_date") or not data.get("start_time"):
        raise ValidationError("scheduled_date and start_time are required")

    # Calculate end_time from start_time + duration if not provided
    if not data.get("end_time"):
        try:
            start = datetime.strptime(data["start_time"], "%H:%M")
        except ValueError:
            raise ValidationError("start_time must be in HH:MM format")
        duration = data.get("duration_min", 30)
        end = start + timedelta(minutes=duration)
        data["end_time"] = end.strftime("%H:%M")

    new_start = data["start_time"][:5]
    new_end = data["end_time"][:5]

    # Reject voice-agent bookings outside the published availability — the
    # LLM only ever sees offered slots, so anything else is a hallucination.
    # Manual UI bookings are exempt: staff may book outside hours intentionally.
    if data.get("source") == "voice_agent":
        from app.features.availability.service import get_available_slots_for_date

        duration = data.get("duration_min", 30)
        offered = get_available_slots_for_date(company_id, data["scheduled_date"], duration)
        if not any(s["start_time"] == new_start for s in offered):
            raise ValidationError(
                f"{new_start} on {data['scheduled_date']} is not an offered slot"
            )

    # Check for conflicting appointments
    existing = repo.get_appointments_for_date(company_id, data["scheduled_date"])
    for appt in existing:
        appt_start = appt["start_time"][:5]
        appt_end = appt["end_time"][:5]
        if new_start < appt_end and new_end > appt_start:
            raise ValidationError(
                f"Time slot conflicts with existing appointment at {appt_start}-{appt_end}"
            )

    return repo.create_appointment(company_id, **data)


def update_appointment(company_id: str, appointment_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = repo.get_appointment_by_id(appointment_id, company_id)
    if not existing:
        raise NotFoundError("Appointment not found")

    valid_statuses = ["confirmed", "cancelled", "completed", "no_show"]
    if data.get("status") and data["status"] not in valid_statuses:
        raise ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")

    updated = repo.update_appointment(appointment_id, company_id, **data)
    if not updated:
        raise NotFoundError("Appointment not found")
    return updated


def cancel_appointment(company_id: str, appointment_id: str) -> Dict[str, Any]:
    return update_appointment(company_id, appointment_id, {"status": "cancelled"})


def delete_appointment(company_id: str, appointment_id: str) -> None:
    deleted = repo.delete_appointment(appointment_id, company_id)
    if not deleted:
        raise NotFoundError("Appointment not found")
