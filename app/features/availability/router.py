"""
Availability — HTTP endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.availability import service
from app.features.availability.schemas import (
    BulkScheduleRequest,
    ExceptionRequest,
)

router = APIRouter(prefix="/availability", tags=["availability"])


# ---------------------------------------------------------------------------
# Weekly schedule
# ---------------------------------------------------------------------------

@router.get("/schedule")
async def get_schedule(current_user: UserContext = Depends(get_current_company)):
    schedules = service.get_weekly_schedule(current_user.company_id)
    return {"schedules": schedules}


@router.put("/schedule")
async def set_schedule(body: BulkScheduleRequest, current_user: UserContext = Depends(get_current_company)):
    slots = [s.model_dump() for s in body.slots]
    created = service.set_weekly_schedule(current_user.company_id, slots)
    return {"schedules": created}


# ---------------------------------------------------------------------------
# Available slots (public-friendly — used by voice agent too)
# ---------------------------------------------------------------------------

@router.get("/slots/{date}")
async def get_available_slots(date: str, duration: int = 30, current_user: UserContext = Depends(get_current_company)):
    slots = service.get_available_slots_for_date(current_user.company_id, date, duration)
    return {"date": date, "slots": slots}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

@router.get("/exceptions")
async def get_exceptions(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: UserContext = Depends(get_current_company),
):
    exceptions = service.get_exceptions(current_user.company_id, from_date, to_date)
    return {"exceptions": exceptions}


@router.post("/exceptions")
async def create_exception(body: ExceptionRequest, current_user: UserContext = Depends(get_current_company)):
    exc = service.create_exception(current_user.company_id, body.model_dump())
    return exc


@router.delete("/exceptions/{exception_id}")
async def delete_exception(exception_id: str, current_user: UserContext = Depends(get_current_company)):
    service.delete_exception(current_user.company_id, exception_id)
    return {"detail": "Exception deleted"}
