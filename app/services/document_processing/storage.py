"""
Storage utilities for uploading and managing documents in Supabase.
"""

from pathlib import Path
from supabase import create_client
from app.core.config import settings


# Supabase bucket name for documents
DOCUMENTS_BUCKET = "documents"


def get_supabase_storage_client():
    """
    Get Supabase client for storage operations.

    Returns:
        Supabase client instance

    Raises:
        ValueError: If Supabase credentials are not configured
    """
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("Supabase URL and Key must be configured")
    return create_client(settings.supabase_url, settings.supabase_key)


def get_content_type(filename: str) -> str:
    """
    Get content type based on file extension.

    Args:
        filename: File name with extension

    Returns:
        MIME type string
    """
    extension = Path(filename).suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
    }
    return content_types.get(extension, "application/octet-stream")


async def upload_file_to_supabase(
    file_content: bytes, filename: str, company_id: str, doc_id: str
) -> str:
    """
    Upload a file to Supabase storage.

    Args:
        file_content: Binary file content
        filename: Original filename
        company_id: Company ID for organization
        doc_id: Document ID for unique identification

    Returns:
        Public URL of the uploaded file

    Raises:
        Exception: If upload fails
    """
    try:
        supabase = get_supabase_storage_client()

        # Create a unique path: company_id/doc_id/filename
        file_path = f"{company_id}/{doc_id}/{filename}"

        # Ensure bucket exists with public access and no RLS
        try:
            bucket = supabase.storage.get_bucket(DOCUMENTS_BUCKET)
        except:
            # Create bucket if it doesn't exist with public access
            try:
                supabase.storage.create_bucket(
                    DOCUMENTS_BUCKET,
                    options={
                        "public": True,
                        "file_size_limit": 52428800,  # 50MB
                        "allowed_mime_types": [
                            "application/pdf",
                            "text/plain",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "application/msword",
                        ],
                    },
                )
            except Exception as create_error:
                # Bucket might already exist, continue
                pass

        # Upload file with upsert to overwrite if exists
        try:
            supabase.storage.from_(DOCUMENTS_BUCKET).upload(
                file_path,
                file_content,
                file_options={"content-type": get_content_type(filename), "upsert": "true"},
            )
        except Exception as upload_error:
            # If upload fails, try to remove existing file and upload again
            try:
                supabase.storage.from_(DOCUMENTS_BUCKET).remove([file_path])
            except:
                pass

            supabase.storage.from_(DOCUMENTS_BUCKET).upload(
                file_path,
                file_content,
                file_options={"content-type": get_content_type(filename)},
            )

        # Get public URL
        file_url = supabase.storage.from_(DOCUMENTS_BUCKET).get_public_url(file_path)

        return file_url

    except Exception as e:
        raise Exception(f"Failed to upload file to Supabase: {str(e)}")