"""
Company-related database operations.

All functions are synchronous (the Supabase Python SDK is synchronous).
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.database import db, generate_id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_company(
    name: str,
    email: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    slug: Optional[str] = None,
) -> Dict[str, Any]:
    if email:
        existing = db.table("companies").select("company_id").eq("email", email).execute()
        if existing.data:
            raise ValueError("Company with this email already exists")

    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
        base_slug, counter = slug, 1
        while True:
            dup = db.table("companies").select("company_id").eq("slug", slug).execute()
            if not dup.data:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

    company_data: Dict[str, Any] = {"company_id": generate_id(), "name": name, "slug": slug}
    if email:
        company_data["email"] = email
    if password:
        company_data["password_hash"] = password
    if api_key:
        company_data["api_keys"] = api_key

    res = db.table("companies").insert(company_data).execute()
    return res.data[0]


def get_company_by_id(company_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("company_id", company_id).execute()
    return res.data[0] if res.data else None


def get_company_by_email(email: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("email", email).execute()
    return res.data[0] if res.data else None


def get_company_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("slug", slug).execute()
    return res.data[0] if res.data else None


def get_company_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("api_keys", api_key).execute()
    return res.data[0] if res.data else None


def get_published_company_info(slug: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("companies")
        .select("company_id, name, slug, chatbot_title, chatbot_description, published_at, settings, plan, ls_subscription_status, subscription_ends_at")
        .eq("slug", slug)
        .eq("is_published", True)
        .execute()
    )
    if not res.data:
        return None
    company = res.data[0]
    company.setdefault("chatbot_title", company["slug"])
    company.setdefault("chatbot_description", "")
    if not company["chatbot_title"]:
        company["chatbot_title"] = company["slug"]
    if not company["chatbot_description"]:
        company["chatbot_description"] = ""
    # Extract enable_user_portal from settings JSON, default True for backward compat
    settings_col = company.pop("settings", None) or {}
    company["enable_user_portal"] = settings_col.get("enable_user_portal", True)

    # Return billing fields so the service layer can evaluate plan status
    return company


def authenticate_company(email: str, password: str) -> Optional[Dict[str, Any]]:
    from app.core.security import verify_password

    res = db.table("companies").select("*").eq("email", email).execute()
    if not res.data:
        return None
    company = res.data[0]
    if not verify_password(password, company.get("password_hash", "")):
        return None
    return company


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------

def update_company_slug(company_id: str, slug: str) -> bool:
    existing = (
        db.table("companies")
        .select("company_id")
        .eq("slug", slug)
        .neq("company_id", company_id)
        .execute()
    )
    if existing.data:
        raise ValueError("This slug is already taken by another company")
    res = db.table("companies").update({"slug": slug}).eq("company_id", company_id).execute()
    return len(res.data) > 0


def publish_chatbot(company_id: str, is_published: bool) -> bool:
    update_data: Dict[str, Any] = {"is_published": is_published}
    if is_published:
        update_data["published_at"] = datetime.now(timezone.utc).isoformat()
    res = db.table("companies").update(update_data).eq("company_id", company_id).execute()
    return len(res.data) > 0


def update_theme_preference(company_id: str, theme_preference: str) -> bool:
    res = (
        db.table("companies")
        .update({"theme_preference": theme_preference})
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0


def update_chatbot_info(company_id: str, chatbot_title: str, chatbot_description: str) -> bool:
    res = (
        db.table("companies")
        .update({"chatbot_title": chatbot_title, "chatbot_description": chatbot_description})
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0


def batch_update_settings(
    company_id: str,
    slug: Optional[str] = None,
    chatbot_title: Optional[str] = None,
    chatbot_description: Optional[str] = None,
    is_published: Optional[bool] = None,
    default_model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    tone: Optional[str] = None,
    enable_user_portal: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    update_data: Dict[str, Any] = {}

    if slug is not None:
        dup = (
            db.table("companies")
            .select("company_id")
            .eq("slug", slug)
            .neq("company_id", company_id)
            .execute()
        )
        if dup.data:
            raise ValueError("This slug is already taken by another company")
        update_data["slug"] = slug

    if chatbot_title is not None:
        update_data["chatbot_title"] = chatbot_title
    if chatbot_description is not None:
        update_data["chatbot_description"] = chatbot_description
    if default_model is not None:
        update_data["default_model"] = default_model
    if system_prompt is not None:
        update_data["system_prompt"] = system_prompt
    if tone is not None:
        update_data["tone"] = tone
    if is_published is not None:
        update_data["is_published"] = is_published
        if is_published:
            update_data["published_at"] = datetime.now(timezone.utc).isoformat()

    # Store enable_user_portal in the settings JSON column
    if enable_user_portal is not None:
        company = get_company_by_id(company_id)
        current_settings = (company.get("settings") or {}) if company else {}
        current_settings["enable_user_portal"] = enable_user_portal
        update_data["settings"] = current_settings

    if not update_data:
        return get_company_by_id(company_id)

    res = db.table("companies").update(update_data).eq("company_id", company_id).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# Embed settings
# ---------------------------------------------------------------------------

EMBED_DEFAULTS: Dict[str, Any] = {
    "theme": "dark",
    "position": "right",
    "primaryColor": "#0d9488",
    "headerColor": "",
    "welcomeText": "Hi there! How can we help you today?",
    "subtitleText": "We typically reply instantly",
    "placeholderText": "Type your message...",
    "showHeaderSubtitle": True,
    "hideBranding": False,
    "autoOpenDelay": 0,
    "buttonIcon": "chat",
    "chatTemplate": "default",
    "suggestedMessages": [],
}


def _apply_embed_defaults(embed_settings: Dict[str, Any]) -> Dict[str, Any]:
    return {key: embed_settings.get(key, default) for key, default in EMBED_DEFAULTS.items()}


def get_embed_settings_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    res = (
        db.table("companies")
        .select("settings, is_published")
        .eq("slug", slug)
        .eq("is_published", True)
        .execute()
    )
    if not res.data:
        return None
    settings_col = res.data[0].get("settings") or {}
    return _apply_embed_defaults(settings_col.get("embed") or {})


def get_embed_settings(company_id: str) -> Dict[str, Any]:
    company = get_company_by_id(company_id)
    if not company:
        return {}
    settings_col = company.get("settings") or {}
    return _apply_embed_defaults(settings_col.get("embed") or {})


def update_embed_settings(company_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    company = get_company_by_id(company_id)
    if not company:
        return None
    current_settings = company.get("settings") or {}
    embed = current_settings.get("embed") or {}
    for key, value in kwargs.items():
        if value is not None:
            embed[key] = value
    current_settings["embed"] = embed
    res = (
        db.table("companies")
        .update({"settings": current_settings})
        .eq("company_id", company_id)
        .execute()
    )
    return embed if res.data else None
