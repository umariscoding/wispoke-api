"""
Availability feature — Pydantic schemas.
"""

from typing import Optional, List
from pydantic import BaseModel, field_validator


class ScheduleSlotRequest(BaseModel):
    day_of_week: int  # 0=Sunday, 6=Saturday
    start_time: str   # "09:00"
    end_time: str     # "17:00"
    is_active: bool = True

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, v: int) -> int:
        if v < 0 or v > 6:
            raise ValueError("day_of_week must be 0 (Sunday) through 6 (Saturday)")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("Invalid time value")
        return f"{h:02d}:{m:02d}"


class BulkScheduleRequest(BaseModel):
    """Set the entire weekly schedule at once."""
    slots: List[ScheduleSlotRequest]


class ExceptionRequest(BaseModel):
    exception_date: str       # "2026-04-25"
    is_available: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("exception_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v


class ExceptionUpdateRequest(BaseModel):
    is_available: Optional[bool] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None
