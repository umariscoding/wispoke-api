from pydantic import BaseModel
from typing import Optional


class UserRegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    company_id: str


class UserLoginRequest(BaseModel):
    email: str
    password: str
    company_id: str


class GuestSessionRequest(BaseModel):
    company_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
