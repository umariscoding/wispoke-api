"""
Chat repository — data access for chats and messages.
"""

from typing import Dict, Any, Optional, List
from app.db.operations.chat import (
    create_chat as db_create_chat,
    get_chat_by_id as db_get_chat_by_id,
    fetch_company_chats as db_fetch_company_chats,
    update_chat_title as db_update_chat_title,
    delete_chat as db_delete_chat,
)
from app.db.operations.message import (
    save_message as db_save_message,
    fetch_messages as db_fetch_messages,
)
from app.db.operations.company import get_company_by_id


async def get_company(company_id: str) -> Optional[Dict[str, Any]]:
    return await get_company_by_id(company_id)


async def create_chat(
    company_id: str,
    chat_id: str,
    title: str,
    user_id: str = None,
    session_id: str = None,
) -> Dict[str, Any]:
    return await db_create_chat(
        company_id=company_id,
        chat_id=chat_id,
        title=title,
        user_id=user_id,
        session_id=session_id,
    )


async def get_chat_by_id(chat_id: str) -> Optional[Dict[str, Any]]:
    return await db_get_chat_by_id(chat_id)


async def fetch_company_chats(
    company_id: str, user_id: str = None, session_id: str = None
) -> List[Dict[str, Any]]:
    return await db_fetch_company_chats(
        company_id=company_id, user_id=user_id, session_id=session_id
    )


async def update_chat_title(company_id: str, chat_id: str, title: str) -> bool:
    return await db_update_chat_title(company_id, chat_id, title)


async def delete_chat(company_id: str, chat_id: str) -> bool:
    return await db_delete_chat(company_id, chat_id)


async def save_message(
    company_id: str, chat_id: str, role: str, content: str
) -> Dict[str, Any]:
    return await db_save_message(
        company_id=company_id, chat_id=chat_id, role=role, content=content
    )


def fetch_messages(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    return db_fetch_messages(company_id, chat_id)
