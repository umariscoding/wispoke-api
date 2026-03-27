"""
Documents service — business logic for document upload, processing, and KB management.
No HTTP concepts. Raises domain exceptions.
"""

import logging
from typing import Dict, Any

from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.rag import (
    process_company_document,
    clear_company_knowledge_base,
    clear_company_cache,
    delete_document_vectors,
)
from app.services.document_processing import (
    validate_file_type,
    extract_text_from_file,
    upload_file_to_supabase,
)
from app.features.documents.repository import (
    save_document,
    get_company_documents_paginated,
    delete_document as db_delete_document,
    update_document_doc_id,
    get_or_create_knowledge_base,
)
from app.core.database import generate_id

logger = logging.getLogger(__name__)


async def upload_document(
    company_id: str, file_content: bytes, filename: str, content_type: str
) -> Dict[str, Any]:
    """Upload a binary file, extract text, embed into vector store."""
    if not validate_file_type(filename, content_type):
        raise ValidationError("Unsupported file type. Only PDF, TXT, and DOCX files are supported.")

    if len(file_content) > 10 * 1024 * 1024:
        raise ValidationError("File size too large. Maximum 10MB allowed.")

    kb = get_or_create_knowledge_base(company_id)
    doc_id = generate_id()

    try:
        file_url = await upload_file_to_supabase(
            file_content=file_content, filename=filename, company_id=company_id, doc_id=doc_id
        )
    except Exception as e:
        raise InternalError(f"Failed to upload file to storage: {e}")

    try:
        text_content = await extract_text_from_file(
            file_content=file_content, filename=filename, content_type=content_type
        )
    except Exception as e:
        raise InternalError(f"Failed to extract text from file: {e}")

    document = save_document(
        kb_id=kb["kb_id"],
        filename=filename,
        content=text_content,
        content_type=content_type,
        file_url=file_url,
    )

    update_document_doc_id(document["doc_id"], doc_id)
    document["doc_id"] = doc_id

    success = await process_company_document(
        company_id=company_id, document_content=text_content, doc_id=doc_id
    )
    if not success:
        raise InternalError("Failed to process document")

    return {
        "message": "Document uploaded and processed successfully",
        "document": {**document, "file_url": file_url},
        "knowledge_base": kb,
    }


def list_documents(company_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    result = get_company_documents_paginated(company_id, page, page_size)
    return {
        "documents": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


def get_knowledge_base_info(company_id: str) -> Dict[str, Any]:
    return get_or_create_knowledge_base(company_id)


def delete_document(doc_id: str, company_id: str) -> Dict[str, str]:
    try:
        delete_document_vectors(company_id, doc_id)
    except Exception as e:
        logger.error("Failed to delete vectors for document %s: %s", doc_id, e)

    try:
        clear_company_cache(company_id)
    except Exception as e:
        logger.error("Failed to clear cache for company %s: %s", company_id, e)

    success = db_delete_document(doc_id, company_id)
    if not success:
        raise NotFoundError("Document not found")
    return {"message": "Document deleted successfully"}


def clear_knowledge_base(company_id: str) -> Dict[str, str]:
    success = clear_company_knowledge_base(company_id)
    if not success:
        raise InternalError("Failed to clear knowledge base")
    return {"message": "Knowledge base cleared successfully"}


def clear_rag_cache(company_id: str) -> Dict[str, str]:
    clear_company_cache(company_id)
    return {"message": "RAG cache cleared successfully. New prompts will take effect on next chat message."}
