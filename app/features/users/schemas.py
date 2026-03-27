"""Users feature — request/response schemas."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    company_id: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    company_id: str


class GuestSessionRequest(BaseModel):
    company_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# Responses

class GuestSessionResponse(BaseModel):
    message: str
    session: Dict[str, Any]
    tokens: Dict[str, str]


class UserRegisterResponse(BaseModel):
    message: str
    user: Dict[str, Any]
    tokens: Dict[str, str]


class UserLoginResponse(BaseModel):
    message: str
    user: Dict[str, Any]
    tokens: Dict[str, str]


class UserProfileResponse(BaseModel):
    user_type: str
    user: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None


class SessionValidityResponse(BaseModel):
    valid: bool
    user_info: Dict[str, Any]


class CompanyInfoResponse(BaseModel):
    company: Dict[str, Any]


class CompanyUsersResponse(BaseModel):
    company_id: str
    company_name: str
    total_users: int
    users: List[Dict[str, Any]]
    page: int
    page_size: int
    total_pages: int
