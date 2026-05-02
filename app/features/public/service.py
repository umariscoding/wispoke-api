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
from app.features.billing.service import is_plan_active
from app.features.users.repository import create_guest_session
from app.features.chat.repository import create_chat, get_chat_by_id, save_message


def _apply_plan_gating(company: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce plan-based feature gating on public company info.

    Free users cannot have the user portal enabled.
    Billing fields are stripped from the public response.
    """
    if not is_plan_active(company):
        company["enable_user_portal"] = False

    company.pop("plan", None)
    company.pop("ls_subscription_status", None)
    company.pop("subscription_ends_at", None)
    return company


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
    return _apply_plan_gating(company)


_PRO_EMBED_DEFAULTS = {
    "theme": "dark",
    "position": "right",
    "primaryColor": "#0d9488",
    "headerColor": "",
    "welcomeText": "Hi there! How can we help you today?",
    "subtitleText": "We typically reply instantly",
    "placeholderText": "Type your message...",
    "showHeaderSubtitle": True,
    "chatTemplate": "default",
    "suggestedMessages": [],
    "buttonIcon": "chat",
    "hideBranding": False,
}


def get_embed_settings(company_slug: str) -> Dict[str, Any]:
    settings = get_embed_settings_by_slug(company_slug)
    if not settings:
        raise NotFoundError("Chatbot not found or not published")

    # Plan gating: free users get default values for Pro-only embed fields
    company = get_company_by_slug(company_slug)
    if company and not is_plan_active(company):
        for key, default in _PRO_EMBED_DEFAULTS.items():
            settings[key] = default

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
