"""
Auth service — business logic for company authentication and settings.
No HTTP concepts (no Request, no HTTPException). Raises domain exceptions.
"""

import re
import secrets
from typing import Dict, Any

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.core.security import (
    create_company_tokens,
    refresh_access_token as jwt_refresh_access_token,
    get_current_user_info,
    get_password_hash,
)
from app.core.exceptions import (
    NotFoundError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    InternalError,
)
from app.core.config import get_chatbot_url, settings as app_settings
from app.features.auth.repository import (
    create_company,
    authenticate_company,
    get_company_by_id,
    get_company_by_email,
    update_company_slug as db_update_company_slug,
    update_theme_preference as db_update_theme_preference,
    publish_chatbot as db_publish_chatbot,
    update_chatbot_info as db_update_chatbot_info,
    batch_update_settings as db_batch_update_settings,
    get_embed_settings as db_get_embed_settings,
    update_embed_settings as db_update_embed_settings,
)
from app.features.users.repository import get_users_by_company_paginated

VALID_MODELS = [
    "Llama-instant", "Llama-large", "GPT-OSS-120B",
    "GPT-OSS-20B", "GPT-4o-mini", "GPT-4o", "GPT-4.1", "GPT-4.1-mini",
]
VALID_TONES = ["professional", "friendly", "casual", "formal", "witty"]


def register_company(name: str, email: str, password: str) -> Dict[str, Any]:
    hashed_password = get_password_hash(password)
    company = create_company(name=name, email=email, password=hashed_password)
    tokens = create_company_tokens(company_id=company["company_id"], email=company["email"])
    return {"message": "Company registered successfully", "company": company, "tokens": tokens}


def google_auth_company(credential: str) -> Dict[str, Any]:
    """Verify Google ID token and sign in or register the company."""
    if not app_settings.google_client_id:
        raise ValidationError("Google authentication is not configured")

    try:
        id_info = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            app_settings.google_client_id,
        )
    except ValueError:
        raise AuthenticationError("Invalid Google credential")

    email = id_info.get("email")
    if not email or not id_info.get("email_verified"):
        raise AuthenticationError("Google account email is not verified")

    name = id_info.get("name") or email.split("@")[0]

    # Existing company → login; otherwise → register
    company = get_company_by_email(email)
    if company:
        tokens = create_company_tokens(company_id=company["company_id"], email=company["email"])
        return {"message": "Login successful", "company": company, "tokens": tokens}

    # Generate an unusable password hash for Google-only accounts
    random_password = get_password_hash(secrets.token_hex(32))
    company = create_company(name=name, email=email, password=random_password)
    tokens = create_company_tokens(company_id=company["company_id"], email=company["email"])
    return {"message": "Company registered successfully", "company": company, "tokens": tokens}


def login_company(email: str, password: str) -> Dict[str, Any]:
    company = authenticate_company(email=email, password=password)
    if not company:
        raise AuthenticationError("Invalid email or password")
    tokens = create_company_tokens(company_id=company["company_id"], email=company["email"])
    return {"message": "Login successful", "company": company, "tokens": tokens}


def get_company_profile(company_id: str) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")
    return {"company": company}


def refresh_tokens(refresh_token: str) -> Dict[str, Any]:
    new_access_token = jwt_refresh_access_token(refresh_token)
    if not new_access_token:
        raise AuthenticationError("Invalid refresh token")
    return {"access_token": new_access_token, "token_type": "bearer"}


def verify_token_info(token: str) -> Dict[str, Any]:
    user_info = get_current_user_info(token)
    if not user_info:
        raise AuthenticationError("Invalid token")
    return {"valid": True, "user_info": user_info}


def logout_company(company_id: str) -> Dict[str, Any]:
    return {"message": "Logout successful", "company_id": company_id}


def update_company_slug(company_id: str, slug: str) -> Dict[str, Any]:
    if not re.match(r'^[a-zA-Z0-9\-_]+$', slug):
        raise ValidationError("Slug must contain only letters, numbers, hyphens, and underscores")
    if len(slug) < 3 or len(slug) > 50:
        raise ValidationError("Slug must be between 3 and 50 characters long")

    success = db_update_company_slug(company_id=company_id, slug=slug)
    if not success:
        raise InternalError("Failed to update slug")

    return {
        "message": "Company slug updated successfully",
        "slug": slug,
        "public_url": get_chatbot_url(slug),
    }


def update_theme_preference(company_id: str, theme_preference: str) -> Dict[str, Any]:
    if theme_preference not in ("light", "dark", "system"):
        raise ValidationError("theme_preference must be 'light', 'dark', or 'system'")
    success = db_update_theme_preference(company_id=company_id, theme_preference=theme_preference)
    if not success:
        raise InternalError("Failed to update theme preference")
    return {"message": "Theme preference updated", "theme_preference": theme_preference}


def publish_chatbot(company_id: str, is_published: bool) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    if is_published and not company.get("slug"):
        raise ValidationError("Company must have a slug before publishing. Please set a slug first.")

    success = db_publish_chatbot(company_id=company_id, is_published=is_published)
    if not success:
        raise InternalError("Failed to update publishing status")

    response_data: Dict[str, Any] = {
        "message": f"Chatbot {'published' if is_published else 'unpublished'} successfully",
        "is_published": is_published,
    }
    if is_published and company.get("slug"):
        response_data["public_url"] = get_chatbot_url(company["slug"])
    return response_data


def update_chatbot_info(
    company_id: str, chatbot_title: str = None, chatbot_description: str = None
) -> Dict[str, Any]:
    if chatbot_title is None and chatbot_description is None:
        raise ValidationError("At least one field (chatbot_title or chatbot_description) must be provided")

    success = db_update_chatbot_info(
        company_id=company_id, chatbot_title=chatbot_title, chatbot_description=chatbot_description
    )
    if not success:
        raise InternalError("Failed to update chatbot information")

    response_data: Dict[str, Any] = {"message": "Chatbot information updated successfully"}
    if chatbot_title is not None:
        response_data["chatbot_title"] = chatbot_title
    if chatbot_description is not None:
        response_data["chatbot_description"] = chatbot_description
    return response_data


def get_chatbot_status(company_id: str) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")
    settings_col = company.get("settings") or {}
    user_portal_setting = settings_col.get("enable_user_portal", True)

    # Free users cannot have user portal — force off regardless of setting
    from app.features.billing.service import is_plan_active
    enable_user_portal = user_portal_setting and is_plan_active(company)

    return {
        "company_id": company["company_id"],
        "slug": company.get("slug"),
        "is_published": company.get("is_published", False),
        "published_at": company.get("published_at"),
        "chatbot_title": company.get("chatbot_title"),
        "chatbot_description": company.get("chatbot_description"),
        "enable_user_portal": enable_user_portal,
        "public_url": (
            get_chatbot_url(company["slug"])
            if company.get("slug") and company.get("is_published")
            else None
        ),
    }


def get_company_users(company_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    result = get_users_by_company_paginated(company_id, page, page_size)
    return {
        "company_id": company_id,
        "company_name": company["name"],
        "users": result["items"],
        "total_users": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


def batch_update_settings(company_id: str, **kwargs) -> Dict[str, Any]:
    slug = kwargs.get("slug")
    is_published = kwargs.get("is_published")
    default_model = kwargs.get("default_model")
    tone = kwargs.get("tone")
    enable_user_portal = kwargs.get("enable_user_portal")

    if all(v is None for v in kwargs.values()):
        raise ValidationError("At least one field must be provided")

    if slug is not None:
        if not re.match(r'^[a-z0-9\-]+$', slug):
            raise ValidationError("Slug must contain only lowercase letters, numbers, and hyphens")
        if len(slug) < 3 or len(slug) > 50:
            raise ValidationError("Slug must be between 3 and 50 characters long")

    # Fetch company once — needed for publish checks and plan gating
    from app.features.billing.service import is_plan_active
    company = get_company_by_id(company_id)
    if not company:
        raise NotFoundError("Company not found")

    if is_published:
        if slug is None and not company.get("slug"):
            raise ValidationError("Company must have a slug before publishing")

    if default_model is not None and default_model not in VALID_MODELS:
        raise ValidationError(f"Invalid model. Must be one of: {', '.join(VALID_MODELS)}")

    if tone is not None and tone not in VALID_TONES:
        raise ValidationError(f"Invalid tone. Must be one of: {', '.join(VALID_TONES)}")

    # Plan gating: free users cannot change model, tone, system prompt, or user portal
    if not is_plan_active(company):
        if default_model is not None:
            raise AuthorizationError("Changing the AI model requires a Pro plan.")
        if tone is not None:
            raise AuthorizationError("Changing the tone requires a Pro plan.")
        if kwargs.get("system_prompt") is not None:
            raise AuthorizationError("Custom instructions require a Pro plan.")
        if enable_user_portal is not None:
            raise AuthorizationError("The user portal requires a Pro plan.")

    updated_company = db_batch_update_settings(company_id=company_id, **kwargs)
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


def get_embed_settings(company_id: str) -> Dict[str, Any]:
    settings = db_get_embed_settings(company_id)
    return {"settings": settings}


_FREE_EMBED_FIELDS = {"autoOpenDelay"}


def update_embed_settings(company_id: str, **kwargs) -> Dict[str, Any]:
    from app.features.billing.service import is_plan_active
    company = get_company_by_id(company_id)
    if company and not is_plan_active(company):
        # Free users can only update behavior/launcher fields
        pro_fields = {k for k, v in kwargs.items() if v is not None and k not in _FREE_EMBED_FIELDS}
        if pro_fields:
            raise AuthorizationError("Customizing embed appearance requires a Pro plan.")

    updated_settings = db_update_embed_settings(company_id=company_id, **kwargs)
    if updated_settings is None:
        raise NotFoundError("Company not found")
    return {"message": "Embed settings updated successfully", "settings": updated_settings}
