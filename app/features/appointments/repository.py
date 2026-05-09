"""
Appointments — database operations.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.database import db, generate_id


def get_appointments(company_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
                     status: Optional[str] = None) -> List[Dict[str, Any]]:
    query = db.table("appointments").select("*").eq("company_id", company_id)
    if from_date:
        query = query.gte("scheduled_date", from_date)
    if to_date:
        query = query.lte("scheduled_date", to_date)
    if status:
        query = query.eq("status", status)
    res = query.order("scheduled_date").order("start_time").execute()
    return res.data or []


def get_appointment_by_id(appointment_id: str, company_id: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("appointments")
        .select("*")
        .eq("appointment_id", appointment_id)
        .eq("company_id", company_id)
        .execute()
    )
    return res.data[0] if res.data else None


def get_upcoming_by_phone(company_id: str, phone: str) -> List[Dict[str, Any]]:
    """Find non-cancelled appointments for a phone number, today onwards.

    Used by the voice agent to spot reschedule/cancel intents — and to greet
    a returning caller with context ("I see you have a 3 PM Wednesday").
    """
    today = datetime.now(timezone.utc).date().isoformat()
    res = (
        db.table("appointments")
        .select("*")
        .eq("company_id", company_id)
        .eq("caller_phone", phone)
        .neq("status", "cancelled")
        .gte("scheduled_date", today)
        .order("scheduled_date")
        .order("start_time")
        .execute()
    )
    return res.data or []


def get_appointments_for_date(company_id: str, date: str) -> List[Dict[str, Any]]:
    res = (
        db.table("appointments")
        .select("*")
        .eq("company_id", company_id)
        .eq("scheduled_date", date)
        .neq("status", "cancelled")
        .order("start_time")
        .execute()
    )
    return res.data or []


def create_appointment(company_id: str, **kwargs: Any) -> Dict[str, Any]:
    data = {
        "appointment_id": generate_id(),
        "company_id": company_id,
        **{k: v for k, v in kwargs.items() if v is not None},
    }
    res = db.table("appointments").insert(data).execute()
    return res.data[0]


def update_appointment(appointment_id: str, company_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    if not update_data:
        return get_appointment_by_id(appointment_id, company_id)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        db.table("appointments")
        .update(update_data)
        .eq("appointment_id", appointment_id)
        .eq("company_id", company_id)
        .execute()
    )
    return res.data[0] if res.data else None


def delete_appointment(appointment_id: str, company_id: str) -> bool:
    res = (
        db.table("appointments")
        .delete()
        .eq("appointment_id", appointment_id)
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0
