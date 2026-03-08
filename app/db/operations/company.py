"""
Company-related database operations.
"""

from typing import Dict, Any, Optional
from .client import db, generate_id


async def create_company(
    name: str,
    email: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    slug: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new company.

    Args:
        name: Company name
        email: Company email (for authentication)
        password: Hashed password (for authentication)
        api_key: API key (for API access)
        slug: Company slug (auto-generated from name if not provided)

    Returns:
        Created company record

    Raises:
        ValueError: If company with email already exists or slug is taken
    """
    import re

    # Check if company with this email already exists
    if email:
        existing = db.table("companies").select("*").eq("email", email).execute()
        if existing.data:
            raise ValueError("Company with this email already exists")

    # Auto-generate slug from company name if not provided
    if not slug:
        # Convert name to URL-friendly slug
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')

        # Check if slug is already taken, append number if needed
        base_slug = slug
        counter = 1
        while True:
            existing_slug = db.table("companies").select("company_id").eq("slug", slug).execute()
            if not existing_slug.data:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

    company_data = {
        "company_id": generate_id(),
        "name": name,
        "slug": slug,
    }

    if email:
        company_data["email"] = email
    if password:
        company_data["password"] = password
    if api_key:
        company_data["api_key"] = api_key

    res = db.table("companies").insert(company_data).execute()
    return res.data[0]


async def get_company_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Get company by API key."""
    res = db.table("companies").select("*").eq("api_key", api_key).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_company_by_id(company_id: str) -> Optional[Dict[str, Any]]:
    """Get company by ID."""
    res = db.table("companies").select("*").eq("company_id", company_id).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_company_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """
    Get company by slug.

    Args:
        slug: Company slug (subdomain)

    Returns:
        Company record or None if not found
    """
    res = db.table("companies").select("*").eq("slug", slug).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_published_company_info(slug: str) -> Optional[Dict[str, Any]]:
    """
    Get published company chatbot information by slug.

    Args:
        slug: Company slug (subdomain)

    Returns:
        Company record with chatbot info or None if not found/published
    """
    res = (
        db.table("companies")
        .select("company_id, name, slug, chatbot_title, chatbot_description, published_at")
        .eq("slug", slug)
        .eq("is_published", True)
        .execute()
    )
    if not res.data:
        return None

    company = res.data[0]
    # Use slug as default if chatbot_title is not set
    if not company.get("chatbot_title"):
        company["chatbot_title"] = company["slug"]
    # Use empty string as default if chatbot_description is not set
    if not company.get("chatbot_description"):
        company["chatbot_description"] = ""

    return company


async def authenticate_company(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a company with email and password.

    Args:
        email: Company email
        password: Hashed password to verify

    Returns:
        Company record if authentication successful, None otherwise
    """
    from app.auth import verify_password

    # Get company by email
    res = db.table("companies").select("*").eq("email", email).execute()
    if not res.data:
        return None

    company = res.data[0]

    # Verify password
    if not verify_password(password, company.get("password", "")):
        return None

    return company


async def update_company_slug(company_id: str, slug: str) -> bool:
    """
    Update company slug.

    Args:
        company_id: Company ID
        slug: New slug value

    Returns:
        True if update successful

    Raises:
        ValueError: If slug is already taken
    """
    # Check if slug is already taken by another company
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


async def publish_chatbot(company_id: str, is_published: bool) -> bool:
    """
    Publish or unpublish a company's chatbot.

    Args:
        company_id: Company ID
        is_published: True to publish, False to unpublish

    Returns:
        True if update successful
    """
    import datetime

    update_data = {"is_published": is_published}

    # Set published_at timestamp if publishing
    if is_published:
        update_data["published_at"] = datetime.datetime.utcnow().isoformat()

    res = db.table("companies").update(update_data).eq("company_id", company_id).execute()
    return len(res.data) > 0


async def update_chatbot_info(
    company_id: str, chatbot_title: str, chatbot_description: str
) -> bool:
    """
    Update chatbot information.

    Args:
        company_id: Company ID
        chatbot_title: Chatbot title
        chatbot_description: Chatbot description

    Returns:
        True if update successful
    """
    res = (
        db.table("companies")
        .update({"chatbot_title": chatbot_title, "chatbot_description": chatbot_description})
        .eq("company_id", company_id)
        .execute()
    )
    return len(res.data) > 0


async def batch_update_settings(
    company_id: str,
    slug: Optional[str] = None,
    chatbot_title: Optional[str] = None,
    chatbot_description: Optional[str] = None,
    is_published: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """
    Batch update company settings.

    Args:
        company_id: Company ID
        slug: Optional new slug
        chatbot_title: Optional chatbot title
        chatbot_description: Optional chatbot description
        is_published: Optional publish status

    Returns:
        Updated company record

    Raises:
        ValueError: If slug is already taken or validation fails
    """
    import datetime

    update_data = {}

    # Validate and add slug if provided
    if slug is not None:
        # Check if slug is already taken by another company
        existing = (
            db.table("companies")
            .select("company_id")
            .eq("slug", slug)
            .neq("company_id", company_id)
            .execute()
        )
        if existing.data:
            raise ValueError("This slug is already taken by another company")
        update_data["slug"] = slug

    # Add chatbot info if provided
    if chatbot_title is not None:
        update_data["chatbot_title"] = chatbot_title
    if chatbot_description is not None:
        update_data["chatbot_description"] = chatbot_description

    # Add publish status if provided
    if is_published is not None:
        update_data["is_published"] = is_published
        if is_published:
            update_data["published_at"] = datetime.datetime.utcnow().isoformat()

    # Only update if there's something to update
    if not update_data:
        return await get_company_by_id(company_id)

    res = db.table("companies").update(update_data).eq("company_id", company_id).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_embed_settings(company_id: str) -> Dict[str, Any]:
    """
    Get embed widget settings for a company.

    Args:
        company_id: Company ID

    Returns:
        Embed settings dictionary (from settings.embed or defaults)
    """
    company = await get_company_by_id(company_id)
    if not company:
        return {}

    settings = company.get("settings") or {}
    embed_settings = settings.get("embed") or {}

    # Return with defaults
    return {
        "theme": embed_settings.get("theme", "dark"),
        "position": embed_settings.get("position", "right"),
        "primaryColor": embed_settings.get("primaryColor", "#6366f1"),
        "welcomeText": embed_settings.get("welcomeText", "Hi there! How can we help you today?"),
        "subtitleText": embed_settings.get("subtitleText", "We typically reply instantly"),
    }


async def update_embed_settings(
    company_id: str,
    theme: Optional[str] = None,
    position: Optional[str] = None,
    primary_color: Optional[str] = None,
    welcome_text: Optional[str] = None,
    subtitle_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update embed widget settings for a company.

    Args:
        company_id: Company ID
        theme: Widget theme (dark/light)
        position: Widget position (left/right)
        primary_color: Primary color hex
        welcome_text: Welcome message
        subtitle_text: Subtitle text

    Returns:
        Updated embed settings
    """
    # Get current company settings
    company = await get_company_by_id(company_id)
    if not company:
        return None

    # Get current settings or create empty dict
    current_settings = company.get("settings") or {}
    embed_settings = current_settings.get("embed") or {}

    # Update only provided fields
    if theme is not None:
        embed_settings["theme"] = theme
    if position is not None:
        embed_settings["position"] = position
    if primary_color is not None:
        embed_settings["primaryColor"] = primary_color
    if welcome_text is not None:
        embed_settings["welcomeText"] = welcome_text
    if subtitle_text is not None:
        embed_settings["subtitleText"] = subtitle_text

    # Update settings with embed
    current_settings["embed"] = embed_settings

    # Save to database
    res = (
        db.table("companies")
        .update({"settings": current_settings})
        .eq("company_id", company_id)
        .execute()
    )

    if not res.data:
        return None

    return embed_settings