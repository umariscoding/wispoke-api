"""
Appointments — HTTP endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.appointments import service
from app.features.appointments.schemas import CreateAppointmentRequest, UpdateAppointmentRequest

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
async def list_appointments(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[str] = None,
    current_user: UserContext = Depends(get_current_company),
):
    appointments = service.list_appointments(current_user.company_id, from_date, to_date, status)
    return {"appointments": appointments}


@router.get("/{appointment_id}")
async def get_appointment(appointment_id: str, current_user: UserContext = Depends(get_current_company)):
    return service.get_appointment(current_user.company_id, appointment_id)


@router.post("")
async def create_appointment(body: CreateAppointmentRequest, current_user: UserContext = Depends(get_current_company)):
    return service.create_appointment(current_user.company_id, body.model_dump())


@router.put("/{appointment_id}")
async def update_appointment(
    appointment_id: str,
    body: UpdateAppointmentRequest,
    current_user: UserContext = Depends(get_current_company),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return service.update_appointment(current_user.company_id, appointment_id, data)


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str, current_user: UserContext = Depends(get_current_company)):
    return service.cancel_appointment(current_user.company_id, appointment_id)


@router.delete("/{appointment_id}")
async def delete_appointment(appointment_id: str, current_user: UserContext = Depends(get_current_company)):
    service.delete_appointment(current_user.company_id, appointment_id)
    return {"detail": "Appointment deleted"}
