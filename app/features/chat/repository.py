"""
Chat & message database operations (synchronous).
"""

import time
from typing import Dict, Any, Optional, List

from langchain_core.chat_history import InMemoryChatMessageHistory

from app.core.database import db, generate_id
from app.core.pagination import PaginationParams, make_paginated_result


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

def create_chat(
    company_id: str,
    user_id: Optional[str] = None,
    title: Optional[str] = "New Chat",
    session_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    chat_data: Dict[str, Any] = {
        "chat_id": chat_id or generate_id(),
        "company_id": company_id,
        "user_id": user_id,
        "title": title,
        "is_deleted": False,
        "is_guest": session_id is not None,
    }
    if session_id:
        chat_data["session_id"] = session_id
    res = db.table("chats").insert(chat_data).execute()
    return res.data[0]


def get_chat_by_id(chat_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("chats").select("*").eq("chat_id", chat_id).execute()
    return res.data[0] if res.data else None


def get_chats_by_company(company_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query = (
        db.table("chats").select("*")
        .eq("company_id", company_id).eq("is_deleted", False)
        .order("created_at", desc=True)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    return query.execute().data or []


def fetch_company_chats(
    company_id: str, user_id: Optional[str] = None, session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = (
        db.table("chats").select("*")
        .eq("company_id", company_id).eq("is_deleted", False)
        .order("created_at", desc=True)
    )
    if user_id:
        query = query.eq("user_id", user_id)
    if session_id:
        query = query.eq("session_id", session_id)
    return query.execute().data or []


def fetch_company_chats_paginated(
    company_id: str, user_id: Optional[str] = None,
    session_id: Optional[str] = None, page: int = 1, page_size: int = 20,
) -> dict:
    p = PaginationParams(page, page_size)
    count_q = db.table("chats").select("chat_id", count="exact").eq("company_id", company_id).eq("is_deleted", False)
    if user_id:
        count_q = count_q.eq("user_id", user_id)
    if session_id:
        count_q = count_q.eq("session_id", session_id)
    total = count_q.execute().count or 0

    data_q = (
        db.table("chats").select("*")
        .eq("company_id", company_id).eq("is_deleted", False)
        .order("created_at", desc=True).range(p.range_start, p.range_end)
    )
    if user_id:
        data_q = data_q.eq("user_id", user_id)
    if session_id:
        data_q = data_q.eq("session_id", session_id)
    return make_paginated_result(data_q.execute().data or [], total, page, page_size)


def verify_chat_access(
    company_id: str, chat_id: str,
    user_id: Optional[str] = None, session_id: Optional[str] = None,
) -> bool:
    query = db.table("chats").select("chat_id").eq("company_id", company_id).eq("chat_id", chat_id).eq("is_deleted", False)
    if user_id:
        query = query.eq("user_id", user_id)
    if session_id:
        query = query.eq("session_id", session_id)
    return bool(query.execute().data)


def update_chat_title(company_id: str, chat_id: str, title: str) -> bool:
    res = db.table("chats").update({"title": title}).eq("chat_id", chat_id).eq("company_id", company_id).execute()
    return len(res.data) > 0


def delete_chat(company_id: str, chat_id: str) -> bool:
    res = db.table("chats").update({"is_deleted": True}).eq("chat_id", chat_id).eq("company_id", company_id).execute()
    return len(res.data) > 0


def fetch_all_chats_by_company(company_id: str) -> List[Dict[str, Any]]:
    return db.table("chats").select("*").eq("company_id", company_id).eq("is_deleted", False).execute().data or []


def load_session_history(company_id: str, chat_id: str) -> InMemoryChatMessageHistory:
    history = InMemoryChatMessageHistory()
    for msg in fetch_messages(company_id, chat_id):
        if msg["role"] == "human":
            history.add_user_message(msg["content"])
        elif msg["role"] == "ai":
            history.add_ai_message(msg["content"])
    return history


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def fetch_messages(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    return (
        db.table("messages").select("*")
        .eq("company_id", company_id).eq("chat_id", chat_id)
        .order("created_at", desc=False).execute()
    ).data or []


def fetch_messages_paginated(
    company_id: str, chat_id: str, page: int = 1, page_size: int = 50,
) -> dict:
    p = PaginationParams(page, page_size)
    total = (
        db.table("messages").select("message_id", count="exact")
        .eq("company_id", company_id).eq("chat_id", chat_id).execute()
    ).count or 0
    data = (
        db.table("messages").select("*")
        .eq("company_id", company_id).eq("chat_id", chat_id)
        .order("created_at", desc=False).range(p.range_start, p.range_end).execute()
    ).data or []
    return make_paginated_result(data, total, page, page_size)


def save_message(company_id: str, chat_id: str, role: str, content: str) -> Dict[str, Any]:
    return db.table("messages").insert({
        "message_id": generate_id(), "company_id": company_id,
        "chat_id": chat_id, "role": role, "content": content,
        "timestamp": int(time.time() * 1000),
    }).execute().data[0]


def get_messages_by_chat(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    return fetch_messages(company_id, chat_id)


def fetch_all_messages_by_company(company_id: str) -> List[Dict[str, Any]]:
    return db.table("messages").select("*").eq("company_id", company_id).execute().data or []
