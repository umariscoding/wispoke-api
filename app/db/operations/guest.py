"""
Guest session-related database operations.
"""

from typing import Dict, Any, Optional
from .client import db, generate_id
from datetime import datetime, timedelta

async def create_guest_session(
    company_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new guest session.

    Args:
        company_id: Company ID
        ip_address: Client IP address (optional)
        user_agent: Client user agent string (optional)

    Returns:
        Created guest session record with auto-generated session_id
    """
    expires_at = datetime.utcnow() + timedelta(hours=24)

    session_data = {
        "session_id": generate_id(),
        "company_id": company_id,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }

    # Add optional fields if provided
    if ip_address:
        session_data["ip_address"] = ip_address
    if user_agent:
        session_data["user_agent"] = user_agent

    res = db.table("guest_sessions").insert(session_data).execute()
    return res.data[0]


async def get_guest_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get guest session by ID."""
    res = db.table("guest_sessions").select("*").eq("session_id", session_id).execute()
    if not res.data:
        return None
    return res.data[0]