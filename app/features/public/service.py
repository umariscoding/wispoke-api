"""
Public service — business logic for public chatbot endpoints.
No HTTP concepts. Raises domain exceptions.
"""

import uuid
import json
from typing import Dict, Any

from app.core.exceptions import NotFoundError
from app.services.rag import stream_company_response
from app.features.auth.repository import get_published_company_info, get_company_by_slug, get_embed_settings_by_slug
from app.features.users.repository import create_guest_session
from app.features.chat.repository import create_chat, get_chat_by_id, save_message


def get_chatbot_info_by_subdomain(subdomain: str, is_subdomain_request: bool) -> Dict[str, Any]:
    if not is_subdomain_request or not subdomain:
        raise NotFoundError("Chatbot not found. Please check the URL.")
    company = get_published_company_info(subdomain)
    if not company:
        raise NotFoundError("Chatbot not found or not published")
    return company


def get_subdomain_company_info(subdomain: str, is_subdomain_request: bool) -> Dict[str, Any]:
    if not is_subdomain_request or not subdomain:
        raise NotFoundError("Company not found. Please check the URL.")
    company = get_company_by_slug(subdomain)
    if not company:
        raise NotFoundError("Company not found")
    return {
        "company_id": company["company_id"],
        "name": company["name"],
        "slug": company["slug"],
        "chatbot_title": company.get("chatbot_title"),
        "chatbot_description": company.get("chatbot_description"),
        "is_published": company.get("is_published", False),
        "published_at": company.get("published_at"),
    }


def send_public_message(
    company: Dict[str, Any],
    message: str,
    chat_id: str = None,
    model: str = "Llama-large",
    ip_address: str = None,
    user_agent: str = None,
) -> tuple:
    company_id = company["company_id"]
    chat_id = chat_id or str(uuid.uuid4())
    existing_chat = get_chat_by_id(chat_id)

    if not existing_chat:
        guest_session = create_guest_session(
            company_id=company_id, ip_address=ip_address, user_agent=user_agent
        )
        create_chat(
            company_id=company_id,
            chat_id=chat_id,
            title="Public Chat",
            session_id=guest_session["session_id"],
        )
        session_id = guest_session["session_id"]
    else:
        session_id = existing_chat.get("session_id", "")

    save_message(company_id=company_id, chat_id=chat_id, role="human", content=message)

    async def stream_and_save():
        try:
            yield f"data: {json.dumps({'chat_id': chat_id, 'session_id': session_id, 'type': 'start'})}\n\n"

            response_buffer = []
            async for chunk in stream_company_response(
                company_id=company_id, query=message, chat_id=chat_id, llm_model=model
            ):
                response_buffer.append(chunk)
                yield f"data: {json.dumps({'content': chunk, 'type': 'chunk'})}\n\n"

            yield f"data: {json.dumps({'type': 'end'})}\n\n"

            complete_response = "".join(response_buffer)
            if complete_response.strip():
                save_message(
                    company_id=company_id, chat_id=chat_id, role="ai", content=complete_response
                )
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"

    return chat_id, session_id, stream_and_save()


def get_chatbot_info_by_slug(company_slug: str) -> Dict[str, Any]:
    company = get_published_company_info(company_slug)
    if not company:
        raise NotFoundError("Chatbot not found or not published")
    return company


def get_embed_settings(company_slug: str) -> Dict[str, Any]:
    settings = get_embed_settings_by_slug(company_slug)
    if not settings:
        raise NotFoundError("Chatbot not found or not published")
    return {"settings": settings}


def get_public_company_info(company_slug: str) -> Dict[str, Any]:
    company = get_company_by_slug(company_slug)
    if not company:
        raise NotFoundError("Company not found")
    return {
        "company_id": company["company_id"],
        "name": company["name"],
        "slug": company["slug"],
        "chatbot_title": company.get("chatbot_title"),
        "chatbot_description": company.get("chatbot_description"),
        "is_published": company.get("is_published", False),
        "published_at": company.get("published_at"),
    }
