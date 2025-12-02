"""
Document processing module.

This module provides functionality for:
- Text splitting and chunking
- File loading and text extraction
- File storage in Supabase
"""

from .text_splitter import split_text_for_txt
from .file_loaders import (
    extract_text_from_file,
    validate_file_type,
    get_file_extension_from_content_type,
)
from .storage import (
    upload_file_to_supabase,
    get_supabase_storage_client,
    get_content_type,
    DOCUMENTS_BUCKET,
)

__all__ = [
    # Text Splitter
    "split_text_for_txt",
    # File Loaders
    "extract_text_from_file",
    "validate_file_type",
    "get_file_extension_from_content_type",
    # Storage
    "upload_file_to_supabase",
    "get_supabase_storage_client",
    "get_content_type",
    "DOCUMENTS_BUCKET",
]