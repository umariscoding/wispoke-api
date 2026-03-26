"""
Auth repository — thin wrapper around company DB operations.
No business logic here, just data access.
"""

from typing import Dict, Any, Optional
from app.db.operations.company import (
    create_company,
    authenticate_company,
    get_company_by_id,
    get_company_by_slug,
    update_company_slug,
    publish_chatbot,
    update_chatbot_info,
    batch_update_settings,
    get_embed_settings,
    update_embed_settings,
)
from app.db.operations.user import get_users_by_company_id


async def create_company_record(name: str, email: str, password_hash: str) -> Dict[str, Any]:
    return await create_company(name=name, email=email, password=password_hash)


async def authenticate_company_record(email: str, password: str) -> Optional[Dict[str, Any]]:
    return await authenticate_company(email=email, password=password)


async def get_company(company_id: str) -> Optional[Dict[str, Any]]:
    return await get_company_by_id(company_id)


async def get_company_by_slug_value(slug: str) -> Optional[Dict[str, Any]]:
    return await get_company_by_slug(slug)


async def update_slug(company_id: str, slug: str) -> bool:
    return await update_company_slug(company_id=company_id, slug=slug)


async def set_publish_status(company_id: str, is_published: bool) -> bool:
    return await publish_chatbot(company_id=company_id, is_published=is_published)


async def update_chatbot_info_record(
    company_id: str, chatbot_title: str, chatbot_description: str
) -> bool:
    return await update_chatbot_info(
        company_id=company_id,
        chatbot_title=chatbot_title,
        chatbot_description=chatbot_description,
    )


async def batch_update_settings_record(
    company_id: str, **kwargs
) -> Optional[Dict[str, Any]]:
    return await batch_update_settings(company_id=company_id, **kwargs)


async def get_embed_settings_record(company_id: str) -> Dict[str, Any]:
    return await get_embed_settings(company_id)


async def update_embed_settings_record(company_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    return await update_embed_settings(company_id=company_id, **kwargs)


async def get_company_users(company_id: str):
    return await get_users_by_company_id(company_id)
