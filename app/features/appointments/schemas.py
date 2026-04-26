"""
Appointments — Pydantic schemas.
"""

from typing import Optional
from pydantic import BaseModel, field_validator


class CreateAppointmentRequest(BaseModel):
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None
    scheduled_date: str        # "2026-04-25"
    start_time: str            # "09:00"
    end_time: Optional[str] = None
    duration_min: int = 30
    service_type: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"

    @field_validator("scheduled_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator("start_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        # Accept HH:MM or HH:MM:SS — Postgres TIME columns serialize with seconds.
        parts = v.split(":")
        if len(parts) not in (2, 3):
            raise ValueError("Time must be in HH:MM format")
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("Invalid time value")
        return f"{h:02d}:{m:02d}"


class UpdateAppointmentRequest(BaseModel):
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None
    scheduled_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: Optional[int] = None
    service_type: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
