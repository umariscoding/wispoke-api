"""
Users router — thin HTTP layer for user management endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any

from app.auth.dependencies import get_current_user, get_current_user_or_guest, UserContext
from app.core.exceptions import AppException
from app.features.users import service
from app.features.users.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    GuestSessionRequest,
)

router = APIRouter(prefix="/users", tags=["user_management"])


def _handle(e: AppException):
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/guest/create")
async def create_guest_session(
    data: GuestSessionRequest, request: Request
) -> Dict[str, Any]:
    try:
        ip_address = data.ip_address or (request.client.host if request.client else "unknown")
        user_agent = data.user_agent or request.headers.get("user-agent", "")
        return await service.create_guest_session(data.company_id, ip_address, user_agent)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create guest session: {str(e)}")


@router.post("/register")
async def register_user(data: UserRegisterRequest) -> Dict[str, Any]:
    try:
        return await service.register_user(
            data.company_id, data.email, data.password, data.name
        )
    except AppException as e:
        _handle(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register user: {str(e)}")


@router.post("/login")
async def login_user(data: UserLoginRequest) -> Dict[str, Any]:
    try:
        return await service.login_user(data.company_id, data.email, data.password)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.get("/profile")
async def get_user_profile(
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    try:
        return await service.get_user_profile(current_user.user_id, current_user.user_type)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")


@router.get("/session/check")
async def check_session_validity(
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    try:
        return await service.check_session_validity(
            current_user.user_id, current_user.company_id,
            current_user.email, current_user.user_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session check failed: {str(e)}")


@router.get("/company/{company_id}/info")
async def get_company_info(
    company_id: str,
    current_user: UserContext = Depends(get_current_user_or_guest),
) -> Dict[str, Any]:
    try:
        return await service.get_company_info(company_id, current_user.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get company info: {str(e)}")


@router.get("/company/{company_id}/users")
async def get_company_users(
    company_id: str,
    current_user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        return await service.get_company_users(
            company_id, current_user.company_id, current_user.is_company()
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get company users: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "user_management"}
