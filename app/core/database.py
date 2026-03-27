"""
Database client singleton and utilities.

The Supabase Python SDK is synchronous, so all repository functions
are plain (non-async) functions. The client is lazily initialized
on first access via a proxy.
"""

import uuid
from typing import Optional
from supabase import Client


_db: Optional[Client] = None


def get_db() -> Client:
    """Return the Supabase client singleton (created on first call)."""
    global _db
    if _db is None:
        from supabase import create_client
        from app.core.config import settings

        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
        _db = create_client(settings.supabase_url, settings.supabase_key)
    return _db


class _LazyDB:
    """Proxy that defers Supabase client creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_db(), name)


db: Client = _LazyDB()  # type: ignore[assignment]


def generate_id() -> str:
    """Generate a UUID-v4 string for primary keys."""
    return str(uuid.uuid4())
