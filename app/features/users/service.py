"""
Users service — business logic for user registration, login, guest sessions.
No HTTP concepts. Raises domain exceptions.
"""

from typing import Dict, Any

from app.core.security import create_user_tokens, create_guest_tokens
from app.core.exceptions import (
    NotFoundError,
    AuthenticationError,
    ValidationError,
    AuthorizationError,
)
from app.features.users.repository import (
    create_user,
    authenticate_user,
    get_user_by_id,
    get_users_by_company_paginated,
    create_guest_session as db_create_guest_session,
    get_guest_session,
)
from app.features.auth.repository import get_company_by_id


def create_guest_session(
    company_id: str, ip_address: str, user_agent: str
) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    session = db_create_guest_session(
        company_id=company_id, ip_address=ip_address, user_agent=user_agent
    )
    tokens = create_guest_tokens(session_id=session["session_id"], company_id=company_id)
    return {
        "message": "Guest session created successfully",
        "session": {
            "session_id": session["session_id"],
            "company_id": session["company_id"],
            "ip_address": session.get("ip_address"),
            "user_agent": session.get("user_agent"),
            "created_at": session.get("created_at"),
            "expires_at": session["expires_at"],
        },
        "tokens": tokens,
    }


def register_user(
    company_id: str, email: str, password: str, name: str
) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    try:
        user = create_user(company_id=company_id, email=email, password=password, name=name)
    except ValueError as e:
        if "already exists" in str(e):
            raise ValidationError("User with this email already exists in this company")
        raise

    tokens = create_user_tokens(
        user_id=user["user_id"], company_id=user["company_id"], email=user["email"]
    )
    return {
        "message": "User registered successfully",
        "user": {
            "user_id": user["user_id"],
            "company_id": user["company_id"],
            "email": user["email"],
            "name": user["name"],
            "is_anonymous": user["is_anonymous"],
            "created_at": user.get("created_at"),
        },
        "tokens": tokens,
    }


def login_user(company_id: str, email: str, password: str) -> Dict[str, Any]:
    user = authenticate_user(company_id=company_id, email=email, password=password)
    if not user:
        raise AuthenticationError("Invalid email or password")
    tokens = create_user_tokens(
        user_id=user["user_id"], company_id=user["company_id"], email=user["email"]
    )
    return {"message": "Login successful", "user": user, "tokens": tokens}


def get_user_profile(user_id: str, user_type: str) -> Dict[str, Any]:
    if user_type == "guest":
        session = get_guest_session(user_id)
        if not session:
            raise NotFoundError("Guest session not found or expired")
        return {
            "session": {
                "session_id": session["session_id"],
                "company_id": session["company_id"],
                "ip_address": session.get("ip_address"),
                "user_agent": session.get("user_agent"),
                "created_at": session.get("created_at"),
                "expires_at": session["expires_at"],
            },
            "user_type": "guest",
        }

    user = get_user_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    return {
        "user": {
            "user_id": user["user_id"],
            "company_id": user["company_id"],
            "email": user["email"],
            "name": user["name"],
            "is_anonymous": user["is_anonymous"],
            "created_at": user.get("created_at"),
        },
        "user_type": "user",
    }


def check_session_validity(
    user_id: str, company_id: str, email: str, user_type: str
) -> Dict[str, Any]:
    return {
        "valid": True,
        "user_info": {
            "user_id": user_id,
            "company_id": company_id,
            "email": email,
            "user_type": user_type,
        },
    }


def get_company_info(company_id: str, requesting_company_id: str) -> Dict[str, Any]:
    if requesting_company_id != company_id:
        raise AuthorizationError("Access denied: You can only access your own company's information")
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")
    return {
        "company": {
            "company_id": company["company_id"],
            "name": company["name"],
            "status": company.get("status", "active"),
        }
    }


def get_company_users(
    company_id: str, requesting_user_company_id: str, is_company: bool,
    page: int = 1, page_size: int = 20,
) -> Dict[str, Any]:
    if not is_company:
        raise AuthorizationError("Access denied: Only company admins can view user lists")
    if requesting_user_company_id != company_id:
        raise AuthorizationError("Access denied: You can only access your own company's users")

    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    result = get_users_by_company_paginated(company_id, page, page_size)
    return {
        "company_id": company_id,
        "company_name": company["name"],
        "total_users": result["total"],
        "users": result["items"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }
