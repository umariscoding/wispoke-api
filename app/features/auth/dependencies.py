"""
FastAPI authentication dependencies for JWT validation.

All DB calls are synchronous (matching the Supabase SDK).
They are called directly inside async dependencies — acceptable because
the Supabase client performs fast network I/O, not CPU-bound work.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.core.security import get_current_user_info
from app.features.auth.repository import get_company_by_id
from app.features.users.repository import get_user_by_id, get_guest_session

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


class UserContext:
    """Authenticated user context carried through the request."""

    __slots__ = ("user_id", "company_id", "user_type", "email")

    def __init__(self, user_id: str, company_id: str, user_type: str, email: Optional[str] = None):
        self.user_id = user_id
        self.company_id = company_id
        self.user_type = user_type
        self.email = email

    def is_company(self) -> bool:
        return self.user_type == "company"

    def is_user(self) -> bool:
        return self.user_type == "user"

    def is_guest(self) -> bool:
        return self.user_type == "guest"


def _unauthorized(detail: str = "Invalid authentication credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
    user_info = get_current_user_info(credentials.credentials)
    if not user_info:
        raise _unauthorized()

    user_type = user_info.get("user_type")
    if not user_type:
        raise _unauthorized("Invalid token payload")

    if user_type == "company":
        company_id = user_info.get("company_id")
        if not company_id:
            raise _unauthorized("Invalid token payload")
        company = get_company_by_id(company_id)
        if not company:
            raise _unauthorized("Company not found")
        return UserContext(company_id, company["company_id"], "company", user_info.get("email"))

    user_id = user_info.get("user_id")
    if not user_id:
        raise _unauthorized("Invalid token payload")

    if user_type == "user":
        user = get_user_by_id(user_id)
        if not user:
            raise _unauthorized("User not found")
        return UserContext(user_id, user["company_id"], "user", user_info.get("email"))

    if user_type == "guest":
        session = get_guest_session(user_id)
        if not session:
            raise _unauthorized("Guest session not found or expired")
        return UserContext(user_id, session["company_id"], "guest")

    raise _unauthorized("Unknown user type")


async def get_current_company(
    current_user: UserContext = Depends(get_current_user),
) -> UserContext:
    if not current_user.is_company():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company access required")
    return current_user


async def get_current_user_or_guest(
    current_user: UserContext = Depends(get_current_user),
) -> UserContext:
    if current_user.is_company():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User or guest access required")
    return current_user


async def get_company_context(
    current_user: UserContext = Depends(get_current_user),
) -> str:
    return current_user.company_id


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
) -> Optional[UserContext]:
    if not credentials:
        return None
    try:
        user_info = get_current_user_info(credentials.credentials)
        if not user_info:
            return None
        user_id = user_info.get("user_id")
        company_id = user_info.get("company_id")
        user_type = user_info.get("user_type")
        if not user_type:
            return None
        if user_type == "company":
            company_id = user_info.get("company_id")
            user_id = company_id
        if not user_id or not company_id:
            return None
        return UserContext(user_id, company_id, user_type, user_info.get("email"))
    except Exception:
        return None
