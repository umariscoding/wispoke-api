"""
Availability — database operations.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.core.database import db, generate_id


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

def get_schedules(company_id: str) -> List[Dict[str, Any]]:
    res = (
        db.table("availability_schedules")
        .select("*")
        .eq("company_id", company_id)
        .order("day_of_week")
        .order("start_time")
        .execute()
    )
    return res.data or []


def create_schedule_slot(company_id: str, day_of_week: int, start_time: str, end_time: str, is_active: bool = True) -> Dict[str, Any]:
    data = {
        "schedule_id": generate_id(),
        "company_id": company_id,
        "day_of_week": day_of_week,
        "start_time": start_time,
        "end_time": end_time,
        "is_active": is_active,
    }
    res = db.table("availability_schedules").insert(data).execute()
    return res.data[0]


def delete_schedules_for_company(company_id: str) -> None:
    db.table("availability_schedules").delete().eq("company_id", company_id).execute()


def update_schedule_slot(schedule_id: str, company_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    if not update_data:
        return None
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        db.table("availability_schedules")
        .update(update_data)
        .eq("schedule_id", schedule_id)
        .eq("company_id", company_id)
        .execute()
    )
    return res.data[0] if res.data else None


def delete_schedule_slot(schedule_id: str, company_id: str) -> bool:
    res = (
        db.table("availability_schedules")
        .delete()
        .eq("schedule_id", schedule_id)
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

def get_exceptions(company_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None) -> List[Dict[str, Any]]:
    query = db.table("availability_exceptions").select("*").eq("company_id", company_id)
    if from_date:
        query = query.gte("exception_date", from_date)
    if to_date:
        query = query.lte("exception_date", to_date)
    res = query.order("exception_date").execute()
    return res.data or []


def create_exception(company_id: str, exception_date: str, is_available: bool = False,
                     start_time: Optional[str] = None, end_time: Optional[str] = None,
                     reason: Optional[str] = None) -> Dict[str, Any]:
    data = {
        "exception_id": generate_id(),
        "company_id": company_id,
        "exception_date": exception_date,
        "is_available": is_available,
    }
    if start_time:
        data["start_time"] = start_time
    if end_time:
        data["end_time"] = end_time
    if reason:
        data["reason"] = reason
    res = db.table("availability_exceptions").insert(data).execute()
    return res.data[0]


def delete_exception(exception_id: str, company_id: str) -> bool:
    res = (
        db.table("availability_exceptions")
        .delete()
        .eq("exception_id", exception_id)
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0
