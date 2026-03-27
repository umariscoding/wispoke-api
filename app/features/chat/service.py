"""
Chat service — business logic for chat messaging, history, and management.
No HTTP concepts. Raises domain exceptions.
"""

import uuid
import json
import logging
from io import StringIO
from typing import Dict, Any, AsyncGenerator

from app.core.exceptions import NotFoundError
from app.services.rag import (
    stream_company_response,
    get_pinecone_client,
    get_company_index_name,
    clear_company_cache,
)
from app.features.chat.repository import (
    create_chat,
    get_chat_by_id,
    fetch_company_chats_paginated,
    verify_chat_access,
    update_chat_title as db_update_chat_title,
    delete_chat as db_delete_chat,
    save_message,
    fetch_messages_paginated,
)
from app.features.auth.repository import get_company_by_id

logger = logging.getLogger(__name__)


def _safe_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def ensure_company_knowledge_base(company_id: str) -> None:
    """Best-effort check that the company's KB index has vectors."""
    try:
        index_name = get_company_index_name(company_id)
        pc = get_pinecone_client()
        existing_indexes = [idx["name"] for idx in pc.list_indexes()]
        if index_name not in existing_indexes:
            return
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        if stats.total_vector_count > 0:
            clear_company_cache(company_id)
    except Exception:
        pass


def send_message(
    company_id: str,
    user_id: str,
    user_type: str,
    message: str,
    chat_id: str = None,
    chat_title: str = "New Chat",
    model: str = "Llama-large",
) -> tuple:
    """
    Orchestrate sending a message: ensure KB, create chat if needed, save message.
    Returns (chat_id, async_stream_generator).
    """
    ensure_company_knowledge_base(company_id)

    chat_id = chat_id or str(uuid.uuid4())
    existing_chat = get_chat_by_id(chat_id)

    if not existing_chat:
        msg_user_id = user_id if user_type == "user" else None
        session_id = user_id if user_type == "guest" else None
        create_chat(
            company_id=company_id,
            chat_id=chat_id,
            title=chat_title,
            user_id=msg_user_id,
            session_id=session_id,
        )

    save_message(company_id=company_id, chat_id=chat_id, role="human", content=message)

    response_buffer = StringIO()

    async def stream_and_save() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {_safe_json({'chat_id': chat_id, 'type': 'start'})}\n\n"

            async for chunk in stream_company_response(
                company_id=company_id,
                query=message,
                chat_id=chat_id,
                llm_model=model,
            ):
                response_buffer.write(chunk)
                clean_chunk = chunk.replace(chr(10), " ").replace(chr(13), " ")
                yield f"data: {_safe_json({'content': clean_chunk, 'type': 'chunk'})}\n\n"

            yield f"data: {_safe_json({'type': 'end'})}\n\n"

        except Exception as e:
            error_msg = str(e)
            if "LocalProtocolError" not in error_msg and "Can't send data" not in error_msg:
                yield f"data: {_safe_json({'error': error_msg, 'type': 'error'})}\n\n"
        finally:
            try:
                complete_response = response_buffer.getvalue()
                if complete_response.strip():
                    save_message(
                        company_id=company_id,
                        chat_id=chat_id,
                        role="ai",
                        content=complete_response,
                    )
            except Exception:
                logger.warning("Failed to persist AI response for chat %s", chat_id, exc_info=True)

    return chat_id, stream_and_save()


def get_chat_history(
    company_id: str, user_id: str, user_type: str, chat_id: str,
    page: int = 1, page_size: int = 50,
) -> Dict[str, Any]:
    _user_id = user_id if user_type == "user" else None
    _session_id = user_id if user_type == "guest" else None

    if not verify_chat_access(company_id, chat_id, user_id=_user_id, session_id=_session_id):
        raise NotFoundError("Chat not found or access denied")

    result = fetch_messages_paginated(company_id, chat_id, page, page_size)
    return {
        "messages": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


def list_chats(
    company_id: str, user_id: str, user_type: str,
    page: int = 1, page_size: int = 20,
) -> Dict[str, Any]:
    _user_id = user_id if user_type == "user" else None
    _session_id = user_id if user_type == "guest" else None

    result = fetch_company_chats_paginated(
        company_id=company_id,
        user_id=_user_id,
        session_id=_session_id,
        page=page,
        page_size=page_size,
    )
    return {
        "chats": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


def update_chat_title(
    company_id: str, user_id: str, user_type: str, chat_id: str, title: str
) -> Dict[str, str]:
    _user_id = user_id if user_type == "user" else None
    _session_id = user_id if user_type == "guest" else None

    if not verify_chat_access(company_id, chat_id, user_id=_user_id, session_id=_session_id):
        raise NotFoundError("Chat not found or access denied")

    db_update_chat_title(company_id, chat_id, title)
    return {"message": "Chat title updated successfully"}


def delete_chat(
    company_id: str, user_id: str, user_type: str, chat_id: str
) -> Dict[str, str]:
    _user_id = user_id if user_type == "user" else None
    _session_id = user_id if user_type == "guest" else None

    if not verify_chat_access(company_id, chat_id, user_id=_user_id, session_id=_session_id):
        raise NotFoundError("Chat not found or access denied")

    db_delete_chat(company_id, chat_id)
    return {"message": "Chat deleted successfully"}


def get_company_info(company_id: str) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")
    return {
        "company": {
            "company_id": company["company_id"],
            "name": company["name"],
            "plan": company.get("plan", "free"),
            "status": company.get("status", "active"),
        }
    }
