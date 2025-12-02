"""
Document service module - Re-exports all document processing operations for backward compatibility.

This module has been refactored into smaller, focused modules under app.services.document_processing/.
All functions are re-exported here to maintain backward compatibility with existing code.

New structure:
- app.services.document_processing.text_splitter - Text splitting and chunking
- app.services.document_processing.file_loaders - File loading and text extraction
- app.services.document_processing.storage - Supabase storage operations
"""

from app.services.document_processing import *