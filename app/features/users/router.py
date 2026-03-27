"""
Users router — thin HTTP layer for user management endpoints.
"""

from fastapi import APIRouter, Depends, Request
from typing import Dict, Any

from app.features.auth.dependencies import get_current_user, get_current_user_or_guest, UserContext
from app.features.users import service
from app.features.users.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    GuestSessionRequest,
)

router = APIRouter(prefix="/users", tags=["user_management"])


@router.post("/guest/create")
def create_guest_session(
    data: GuestSessionRequest, request: Request
) -> Dict[str, Any]:
    ip_address = data.ip_address or (request.client.host if request.client else "unknown")
    user_agent = data.user_agent or request.headers.get("user-agent", "")
    return service.create_guest_session(data.company_id, ip_address, user_agent)


@router.post("/register")
def register_user(data: UserRegisterRequest) -> Dict[str, Any]:
    return service.register_user(data.company_id, data.email, data.password, data.name)


@router.post("/login")
def login_user(data: UserLoginRequest) -> Dict[str, Any]:
    return service.login_user(data.company_id, data.email, data.password)


@router.get("/profile")
async def get_user_profile(
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    return service.get_user_profile(current_user.user_id, current_user.user_type)


@router.get("/session/check")
async def check_session_validity(
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    return service.check_session_validity(
        current_user.user_id, current_user.company_id,
        current_user.email, current_user.user_type,
    )


@router.get("/company/{company_id}/info")
async def get_company_info(
    company_id: str,
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    return service.get_company_info(company_id, current_user.company_id)


@router.get("/company/{company_id}/users")
async def get_company_users(
    company_id: str,
    page: int = 1,
    page_size: int = 20,
    current_user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    return service.get_company_users(
        company_id, current_user.company_id, current_user.is_company(),
        page=page, page_size=page_size,
    )


@router.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "user_management"}
