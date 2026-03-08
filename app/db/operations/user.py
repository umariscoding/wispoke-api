"""
User-related database operations.
"""

from typing import Dict, Any, Optional, List
from .client import db, generate_id
from app.utils.password import get_password_hash


async def create_user(
    company_id: str,
    email: str,
    name: Optional[str] = None,
    password: Optional[str] = None,
    is_anonymous: bool = False,
) -> Dict[str, Any]:
    """
    Create a new user.

    Args:
        company_id: Company ID
        email: User email
        name: User name
        password: Hashed password (for authenticated users)
        is_anonymous: Whether user is anonymous

    Returns:
        Created user record

    Raises:
        ValueError: If user with email already exists in this company
    """
    # Check if user already exists
    existing = (
        db.table("company_users")
        .select("*")
        .eq("company_id", company_id)
        .eq("email", email)
        .execute()
    )
    if existing.data:
        raise ValueError("User with this email already exists in this company")

    user_data = {
        "user_id": generate_id(),
        "company_id": company_id,
        "email": email,
        "name": name,
        "is_anonymous": is_anonymous,
    }

    if password:
        user_data["password_hash"] = get_password_hash(password)

    res = db.table("company_users").insert(user_data).execute()
    return res.data[0]


async def get_user_by_email(company_id: str, email: str) -> Optional[Dict[str, Any]]:
    """Get user by email within a company."""
    res = db.table("company_users").select("*")\
        .eq("company_id", company_id)\
        .eq("email", email)\
        .execute()
    if not res.data:
        return None
    return res.data[0]


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    res = db.table("company_users").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return None
    u = res.data[0]
    return {
        "user_id": u["user_id"],
        "company_id": u["company_id"],
        "email": u["email"],
        "name": u["name"],
        "is_anonymous": u["is_anonymous"],
        "created_at": u["created_at"]
    }


async def get_users_by_company_id(company_id: str) -> List[Dict[str, Any]]:
    """Get all users for a company."""
    res = db.table("company_users").select("*").eq("company_id", company_id).execute()
    if not res.data:
        return []
    return [
        {
            "user_id": u["user_id"],
            "company_id": u["company_id"],
            "email": u["email"],
            "name": u["name"],
            "is_anonymous": u["is_anonymous"],
            "created_at": u["created_at"]
        }
        for u in res.data
    ]


async def authenticate_user(
    company_id: str, email: str, password: str
) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user with email and password.

    Args:
        company_id: Company ID
        email: User email
        password: Password to verify

    Returns:
        User record if authentication successful, None otherwise
    """
    from app.auth import verify_password

    # Get user by email and company
    res = (
        db.table("company_users")
        .select("*")
        .eq("company_id", company_id)
        .eq("email", email)
        .execute()
    )
    if not res.data:
        return None

    user = res.data[0]

    # Verify password
    if not verify_password(password, user.get("password_hash", "")):
        return None

    return user