"""
Storage utilities for uploading and managing documents in Supabase.
"""

import logging
from pathlib import Path

from app.core.database import get_db

logger = logging.getLogger(__name__)

DOCUMENTS_BUCKET = "documents"


def get_content_type(filename: str) -> str:
    """Get MIME type from file extension."""
    extension = Path(filename).suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
    }
    return content_types.get(extension, "application/octet-stream")


def _ensure_bucket(supabase) -> None:
    """Create the documents bucket if it doesn't exist."""
    try:
        supabase.storage.get_bucket(DOCUMENTS_BUCKET)
    except Exception:
        try:
            supabase.storage.create_bucket(
                DOCUMENTS_BUCKET,
                options={
                    "public": True,
                    "file_size_limit": 52428800,  # 50 MB
                    "allowed_mime_types": [
                        "application/pdf",
                        "text/plain",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "application/msword",
                    ],
                },
            )
        except Exception:
            # Bucket may already exist (race condition) — safe to continue
            logger.debug("Bucket creation skipped (may already exist)")


async def upload_file_to_supabase(
    file_content: bytes, filename: str, company_id: str, doc_id: str
) -> str:
    """
    Upload a file to Supabase storage and return the public URL.

    Kept as async for compatibility with the document upload router,
    but the underlying Supabase SDK calls are synchronous.
    """
    supabase = get_db()
    file_path = f"{company_id}/{doc_id}/{filename}"

    _ensure_bucket(supabase)

    try:
        supabase.storage.from_(DOCUMENTS_BUCKET).upload(
            file_path,
            file_content,
            file_options={"content-type": get_content_type(filename), "upsert": "true"},
        )
    except Exception:
        # Fallback: remove then re-upload
        try:
            supabase.storage.from_(DOCUMENTS_BUCKET).remove([file_path])
        except Exception:
            logger.debug("Could not remove existing file at %s", file_path)

        supabase.storage.from_(DOCUMENTS_BUCKET).upload(
            file_path,
            file_content,
            file_options={"content-type": get_content_type(filename)},
        )

    return supabase.storage.from_(DOCUMENTS_BUCKET).get_public_url(file_path)


def get_supabase_storage_client():
    """Return the shared Supabase client (for backward compat imports)."""
    return get_db()
