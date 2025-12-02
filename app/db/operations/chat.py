"""
Chat-related database operations.
"""

from typing import Dict, Any, Optional, List
from langchain_core.chat_history import BaseChatMessageHistory

from .client import db, generate_id
from .message import fetch_messages


async def create_chat(
    company_id: str,
    user_id: Optional[str] = None,
    title: Optional[str] = "New Chat",
    session_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new chat.

    Args:
        company_id: Company ID
        user_id: User ID (for registered users)
        title: Chat title
        session_id: Guest session ID (for guest users)
        chat_id: Optional specific chat ID to use

    Returns:
        Created chat record
    """
    chat_data = {
        "chat_id": chat_id or generate_id(),
        "company_id": company_id,
        "user_id": user_id,
        "title": title,
        "is_deleted": False,
        "is_guest": session_id is not None  # True if session_id provided (guest), False otherwise
    }

    # Add session_id if provided (for guest sessions)
    if session_id:
        chat_data["session_id"] = session_id

    res = db.table("chats").insert(chat_data).execute()
    return res.data[0]


async def get_chat_by_id(chat_id: str) -> Optional[Dict[str, Any]]:
    """Get chat by ID."""
    res = db.table("chats").select("*").eq("chat_id", chat_id).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_chats_by_company(company_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all chats for a company, optionally filtered by user."""
    query = db.table("chats").select("*")\
        .eq("company_id", company_id)\
        .eq("is_deleted", False)\
        .order("created_at", desc=True)

    if user_id:
        query = query.eq("user_id", user_id)

    res = query.execute()
    return res.data or []


async def fetch_company_chats(
    company_id: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch chats for a company, optionally filtered by user or guest session.

    Args:
        company_id: Company ID
        user_id: Optional user ID to filter user-specific chats
        session_id: Optional session ID to filter guest chats

    Returns:
        List of chat records
    """
    query = db.table("chats").select("*")\
        .eq("company_id", company_id)\
        .eq("is_deleted", False)\
        .order("created_at", desc=True)

    # Filter by user_id if provided (for registered users)
    if user_id:
        query = query.eq("user_id", user_id)

    # Filter by session_id if provided (for guest users)
    if session_id:
        query = query.eq("session_id", session_id)

    res = query.execute()
    return res.data or []


async def update_chat_title(company_id: str, chat_id: str, title: str) -> bool:
    """Update chat title."""
    res = db.table("chats").update({"title": title})\
        .eq("chat_id", chat_id)\
        .eq("company_id", company_id)\
        .execute()
    return len(res.data) > 0


async def delete_chat(company_id: str, chat_id: str) -> bool:
    """Soft delete a chat."""
    res = db.table("chats").update({"is_deleted": True})\
        .eq("chat_id", chat_id)\
        .eq("company_id", company_id)\
        .execute()
    return len(res.data) > 0


def load_session_history(company_id: str, chat_id: str) -> BaseChatMessageHistory:
    """Load chat message history for a session."""
    history = BaseChatMessageHistory()
    messages = fetch_messages(company_id, chat_id)
    for msg in messages:
        if msg["role"] == "human":
            history.add_user_message(msg["content"])
        elif msg["role"] == "ai":
            history.add_ai_message(msg["content"])
    return history


# Legacy/compatibility functions for old API
async def fetch_all_chats() -> List[Dict[str, Any]]:
    """
    Get all chats across all companies (legacy function).
    WARNING: This doesn't filter by company - use with caution.
    """
    res = db.table("chats").select("*").eq("is_deleted", False).order("created_at", desc=True).execute()
    return res.data or []


async def save_chat(chat_id: str, chat_name: str, company_id: str = "default") -> Dict[str, Any]:
    """
    Save/create a chat with a specific ID (legacy function).

    Args:
        chat_id: Specific chat ID to use
        chat_name: Title for the chat
        company_id: Company ID (defaults to "default" for backward compatibility)

    Returns:
        Created chat record
    """
    res = db.table("chats").insert({
        "chat_id": chat_id,
        "company_id": company_id,
        "title": chat_name,
        "is_deleted": False,
        "is_guest": False  # Legacy function assumes non-guest chats
    }).execute()
    return res.data[0] if res.data else {}


async def delete_all_chats() -> bool:
    """
    Delete all chats (legacy function).
    WARNING: This deletes ALL chats across all companies.
    """
    res = db.table("chats").update({"is_deleted": True}).execute()
    return True