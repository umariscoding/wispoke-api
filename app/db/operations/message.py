"""
Message-related database operations.
"""

from typing import Dict, Any, List, Optional
from .client import db, generate_id


def fetch_messages(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    """Fetch all messages for a chat (synchronous for compatibility)."""
    res = db.table("messages").select("*")\
        .eq("company_id", company_id)\
        .eq("chat_id", chat_id)\
        .order("created_at", desc=False)\
        .execute()
    return res.data or []


async def save_message(
    company_id: str,
    chat_id: str,
    role: str,
    content: str
) -> Dict[str, Any]:
    """
    Save a new message to the database.

    Args:
        company_id: Company ID
        chat_id: Chat ID
        role: Message role (human/ai)
        content: Message content

    Returns:
        Created message record
    """
    import time

    res = db.table("messages").insert({
        "message_id": generate_id(),
        "company_id": company_id,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "timestamp": int(time.time() * 1000)  # Unix timestamp in milliseconds
    }).execute()
    return res.data[0]


async def get_messages_by_chat(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    """Get all messages for a chat."""
    res = db.table("messages").select("*")\
        .eq("company_id", company_id)\
        .eq("chat_id", chat_id)\
        .order("created_at", desc=False)\
        .execute()
    return res.data or []


# Legacy/compatibility functions for old API
async def fetch_messages_old(chat_id: str) -> List[Dict[str, Any]]:
    """
    Fetch messages by chat_id only (legacy function).
    WARNING: Doesn't filter by company_id.
    """
    res = db.table("messages").select("*")\
        .eq("chat_id", chat_id)\
        .order("created_at", desc=False)\
        .execute()
    return res.data or []


async def save_message_old(
    chat_id: str,
    role: str,
    content: str,
    company_id: str = "default"
) -> Dict[str, Any]:
    """
    Save a message with simplified parameters (legacy function).

    Args:
        chat_id: Chat ID
        role: Message role (human/ai)
        content: Message content
        company_id: Company ID (defaults to "default" for backward compatibility)

    Returns:
        Created message record
    """
    import time

    res = db.table("messages").insert({
        "message_id": generate_id(),
        "company_id": company_id,
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "timestamp": int(time.time() * 1000)  # Unix timestamp in milliseconds
    }).execute()
    return res.data[0] if res.data else {}