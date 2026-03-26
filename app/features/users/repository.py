"""
Users repository — data access for users and guest sessions.
"""

from typing import Dict, Any, Optional, List
from app.db.operations.user import (
    create_user as db_create_user,
    authenticate_user as db_authenticate_user,
    get_user_by_id as db_get_user_by_id,
    get_users_by_company_id as db_get_users_by_company_id,
)
from app.db.operations.guest import (
    create_guest_session as db_create_guest_session,
    get_guest_session as db_get_guest_session,
)
from app.db.operations.company import get_company_by_id


async def get_company(company_id: str) -> Optional[Dict[str, Any]]:
    return await get_company_by_id(company_id)


async def create_user(
    company_id: str, email: str, password: str, name: str
) -> Dict[str, Any]:
    return await db_create_user(
        company_id=company_id, email=email, password=password, name=name
    )


async def authenticate_user(
    company_id: str, email: str, password: str
) -> Optional[Dict[str, Any]]:
    return await db_authenticate_user(
        company_id=company_id, email=email, password=password
    )


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    return await db_get_user_by_id(user_id)


async def get_users_by_company(company_id: str) -> List[Dict[str, Any]]:
    return await db_get_users_by_company_id(company_id)


async def create_guest_session(
    company_id: str, ip_address: str = None, user_agent: str = None
) -> Dict[str, Any]:
    return await db_create_guest_session(
        company_id=company_id, ip_address=ip_address, user_agent=user_agent
    )


async def get_guest_session(session_id: str) -> Optional[Dict[str, Any]]:
    return await db_get_guest_session(session_id)
