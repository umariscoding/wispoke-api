"""
User & guest-session database operations (synchronous).
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from app.core.database import db, generate_id
from app.core.security import get_password_hash
from app.core.pagination import PaginationParams, make_paginated_result


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(
    company_id: str, email: str, name: Optional[str] = None,
    password: Optional[str] = None, is_anonymous: bool = False,
) -> Dict[str, Any]:
    existing = db.table("company_users").select("user_id").eq("company_id", company_id).eq("email", email).execute()
    if existing.data:
        raise ValueError("User with this email already exists in this company")
    user_data: Dict[str, Any] = {
        "user_id": generate_id(), "company_id": company_id,
        "email": email, "name": name, "is_anonymous": is_anonymous,
    }
    if password:
        user_data["password_hash"] = get_password_hash(password)
    return db.table("company_users").insert(user_data).execute().data[0]


def get_user_by_email(company_id: str, email: str) -> Optional[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("company_id", company_id).eq("email", email).execute()
    return res.data[0] if res.data else None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return None
    u = res.data[0]
    return {
        "user_id": u["user_id"], "company_id": u["company_id"],
        "email": u["email"], "name": u["name"],
        "is_anonymous": u["is_anonymous"], "created_at": u["created_at"],
    }


def get_users_by_company_id(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("company_id", company_id).execute()
    return [
        {"user_id": u["user_id"], "company_id": u["company_id"], "email": u["email"],
         "name": u["name"], "is_anonymous": u["is_anonymous"], "created_at": u["created_at"]}
        for u in (res.data or [])
    ]


def get_users_by_company_paginated(company_id: str, page: int = 1, page_size: int = 20) -> dict:
    p = PaginationParams(page, page_size)
    total = db.table("company_users").select("user_id", count="exact").eq("company_id", company_id).execute().count or 0
    data = (
        db.table("company_users").select("*").eq("company_id", company_id)
        .order("created_at", desc=True).range(p.range_start, p.range_end).execute()
    ).data or []
    return make_paginated_result(data, total, page, page_size)


def authenticate_user(company_id: str, email: str, password: str) -> Optional[Dict[str, Any]]:
    from app.core.security import verify_password
    res = db.table("company_users").select("*").eq("company_id", company_id).eq("email", email).execute()
    if not res.data:
        return None
    user = res.data[0]
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return user


def fetch_all_users_by_company(company_id: str) -> List[Dict[str, Any]]:
    return db.table("company_users").select("*").eq("company_id", company_id).execute().data or []


# ---------------------------------------------------------------------------
# Guest sessions
# ---------------------------------------------------------------------------

def create_guest_session(
    company_id: str, ip_address: Optional[str] = None, user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    session_data: Dict[str, Any] = {
        "session_id": generate_id(), "company_id": company_id,
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "created_at": now.isoformat(),
    }
    if ip_address:
        session_data["ip_address"] = ip_address
    if user_agent:
        session_data["user_agent"] = user_agent
    return db.table("guest_sessions").insert(session_data).execute().data[0]


def get_guest_session(session_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("guest_sessions").select("*").eq("session_id", session_id).execute()
    return res.data[0] if res.data else None


def fetch_all_guest_sessions_by_company(company_id: str) -> List[Dict[str, Any]]:
    return db.table("guest_sessions").select("*").eq("company_id", company_id).execute().data or []
