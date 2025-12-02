"""
Database client and utility functions.
"""

import uuid
from supabase import create_client, Client
from app.core.config import settings


def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("Supabase URL and Key must be configured in environment variables")
    return create_client(settings.supabase_url, settings.supabase_key)


# Initialize global database client
db: Client = get_supabase_client()


def generate_id() -> str:
    """Generate a unique ID for database records."""
    return str(uuid.uuid4())