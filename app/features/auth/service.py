"""
Auth service — business logic for company authentication and settings.
No HTTP concepts (no Request, no HTTPException). Raises domain exceptions.
"""

import re
from typing import Dict, Any

from app.auth.jwt import (
    create_company_tokens,
    refresh_access_token as jwt_refresh_access_token,
    get_current_user_info,
)
from app.utils.password import get_password_hash
from app.core.exceptions import (
    NotFoundError,
    AuthenticationError,
    ValidationError,
    InternalError,
)
from app.core.config import get_chatbot_url
from app.features.auth import repository as repo


VALID_MODELS = [
    "Llama-instant", "Llama-large", "GPT-OSS-120B",
    "GPT-OSS-20B", "OpenAI", "Claude", "Cohere",
]
VALID_TONES = ["professional", "friendly", "casual", "formal", "witty"]


async def register_company(name: str, email: str, password: str) -> Dict[str, Any]:
    hashed_password = get_password_hash(password)
    company = await repo.create_company_record(name, email, hashed_password)
    tokens = create_company_tokens(
        company_id=company["company_id"], email=company["email"]
    )
    return {"message": "Company registered successfully", "company": company, "tokens": tokens}


async def login_company(email: str, password: str) -> Dict[str, Any]:
    company = await repo.authenticate_company_record(email, password)
    if not company:
        raise AuthenticationError("Invalid email or password")
    tokens = create_company_tokens(
        company_id=company["company_id"], email=company["email"]
    )
    return {"message": "Login successful", "company": company, "tokens": tokens}


async def get_company_profile(company_id: str) -> Dict[str, Any]:
    company = await repo.get_company(company_id)
    if not company:
        raise NotFoundError("Company not found")
    return {"company": company}


async def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    new_access_token = jwt_refresh_access_token(refresh_token)
    if not new_access_token:
        raise AuthenticationError("Invalid refresh token")
    return {"access_token": new_access_token, "token_type": "bearer"}


async def verify_token_info(token: str) -> Dict[str, Any]:
    user_info = get_current_user_info(token)
    if not user_info:
        raise AuthenticationError("Invalid token")
    return {"valid": True, "user_info": user_info}


async def logout_company(company_id: str) -> Dict[str, Any]:
    return {"message": "Logout successful", "company_id": company_id}


async def update_company_slug(company_id: str, slug: str) -> Dict[str, Any]:
    if not re.match(r'^[a-zA-Z0-9-_]+$', slug):
        raise ValidationError("Slug must contain only letters, numbers, hyphens, and underscores")
    if len(slug) < 3 or len(slug) > 50:
        raise ValidationError("Slug must be between 3 and 50 characters long")

    success = await repo.update_slug(company_id, slug)
    if not success:
        raise InternalError("Failed to update slug")

    return {
        "message": "Company slug updated successfully",
        "slug": slug,
        "public_url": get_chatbot_url(slug),
    }


async def publish_chatbot(company_id: str, is_published: bool) -> Dict[str, Any]:
    company = await repo.get_company(company_id)
    if not company:
        raise NotFoundError("Company not found")

    if is_published and not company.get("slug"):
        raise ValidationError("Company must have a slug before publishing. Please set a slug first.")

    success = await repo.set_publish_status(company_id, is_published)
    if not success:
        raise InternalError("Failed to update publishing status")

    response_data = {
        "message": f"Chatbot {'published' if is_published else 'unpublished'} successfully",
        "is_published": is_published,
    }
    if is_published and company.get("slug"):
        response_data["public_url"] = get_chatbot_url(company["slug"])
    return response_data


async def update_chatbot_info(
    company_id: str, chatbot_title: str = None, chatbot_description: str = None
) -> Dict[str, Any]:
    if chatbot_title is None and chatbot_description is None:
        raise ValidationError("At least one field (chatbot_title or chatbot_description) must be provided")

    success = await repo.update_chatbot_info_record(company_id, chatbot_title, chatbot_description)
    if not success:
        raise InternalError("Failed to update chatbot information")

    response_data = {"message": "Chatbot information updated successfully"}
    if chatbot_title is not None:
        response_data["chatbot_title"] = chatbot_title
    if chatbot_description is not None:
        response_data["chatbot_description"] = chatbot_description
    return response_data


async def get_chatbot_status(company_id: str) -> Dict[str, Any]:
    company = await repo.get_company(company_id)
    if not company:
        raise NotFoundError("Company not found")

    return {
        "company_id": company["company_id"],
        "slug": company.get("slug"),
        "is_published": company.get("is_published", False),
        "published_at": company.get("published_at"),
        "chatbot_title": company.get("chatbot_title"),
        "chatbot_description": company.get("chatbot_description"),
        "public_url": get_chatbot_url(company["slug"]) if company.get("slug") and company.get("is_published") else None,
    }


async def get_company_users(company_id: str) -> Dict[str, Any]:
    company = await repo.get_company(company_id)
    if not company:
        raise NotFoundError("Company not found")

    users = await repo.get_company_users(company_id)
    return {
        "company_id": company_id,
        "company_name": company["name"],
        "users": users,
        "total_users": len(users),
    }


async def batch_update_settings(company_id: str, **kwargs) -> Dict[str, Any]:
    slug = kwargs.get("slug")
    is_published = kwargs.get("is_published")
    default_model = kwargs.get("default_model")
    tone = kwargs.get("tone")

    if all(v is None for v in kwargs.values()):
        raise ValidationError("At least one field must be provided")

    if slug is not None:
        if not re.match(r'^[a-z0-9-]+$', slug):
            raise ValidationError("Slug must contain only lowercase letters, numbers, and hyphens")
        if len(slug) < 3 or len(slug) > 50:
            raise ValidationError("Slug must be between 3 and 50 characters long")

    if is_published:
        company = await repo.get_company(company_id)
        if not company:
            raise NotFoundError("Company not found")
        if slug is None and not company.get("slug"):
            raise ValidationError("Company must have a slug before publishing")

    if default_model is not None and default_model not in VALID_MODELS:
        raise ValidationError(f"Invalid model. Must be one of: {', '.join(VALID_MODELS)}")

    if tone is not None and tone not in VALID_TONES:
        raise ValidationError(f"Invalid tone. Must be one of: {', '.join(VALID_TONES)}")

    updated_company = await repo.batch_update_settings_record(company_id=company_id, **kwargs)
    if not updated_company:
        raise InternalError("Failed to update settings")

    # Invalidate RAG chain cache if model or system prompt changed
    if default_model is not None or kwargs.get("system_prompt") is not None or tone is not None:
        try:
            from app.services.rag import clear_company_rag_chain_cache
            clear_company_rag_chain_cache(company_id)
        except Exception:
            pass

    return {"message": "Settings updated successfully", "company": updated_company}


async def get_embed_settings(company_id: str) -> Dict[str, Any]:
    settings = await repo.get_embed_settings_record(company_id)
    return {"settings": settings}


async def update_embed_settings(company_id: str, **kwargs) -> Dict[str, Any]:
    updated_settings = await repo.update_embed_settings_record(company_id, **kwargs)
    if updated_settings is None:
        raise NotFoundError("Company not found")
    return {"message": "Embed settings updated successfully", "settings": updated_settings}
