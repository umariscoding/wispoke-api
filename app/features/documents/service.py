"""
Documents service — business logic for document upload, processing, and KB management.
No HTTP concepts. Raises domain exceptions.
"""

from typing import Dict, Any, List

from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.rag import (
    process_company_document,
    clear_company_knowledge_base,
    clear_company_cache,
)
from app.services.document_processing import (
    validate_file_type,
    extract_text_from_file,
    upload_file_to_supabase,
)
from app.features.documents import repository as repo


async def upload_document(
    company_id: str, file_content: bytes, filename: str, content_type: str
) -> Dict[str, Any]:
    if not validate_file_type(filename, content_type):
        raise ValidationError("Unsupported file type. Only PDF, TXT, and DOCX files are supported.")

    if len(file_content) > 10 * 1024 * 1024:
        raise ValidationError("File size too large. Maximum 10MB allowed.")

    kb = await repo.get_or_create_knowledge_base(company_id)
    doc_id = repo.new_id()

    try:
        file_url = await upload_file_to_supabase(
            file_content=file_content,
            filename=filename,
            company_id=company_id,
            doc_id=doc_id,
        )
    except Exception as e:
        raise InternalError(f"Failed to upload file to storage: {str(e)}")

    try:
        text_content = await extract_text_from_file(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
        )
    except Exception as e:
        raise InternalError(f"Failed to extract text from file: {str(e)}")

    document = await repo.save_document(
        kb_id=kb["kb_id"],
        filename=filename,
        content=text_content,
        content_type=content_type,
        file_url=file_url,
    )

    repo.update_document_doc_id(document["doc_id"], doc_id)
    document["doc_id"] = doc_id

    success = await process_company_document(
        company_id=company_id,
        document_content=text_content,
        doc_id=doc_id,
    )
    if not success:
        raise InternalError("Failed to process document")

    return {
        "message": "Document uploaded and processed successfully",
        "document": {**document, "file_url": file_url},
        "knowledge_base": kb,
    }


async def upload_text_content(
    company_id: str, content: str, filename: str
) -> Dict[str, Any]:
    if len(content.encode('utf-8')) > 10 * 1024 * 1024:
        raise ValidationError("Content size too large. Maximum 10MB allowed.")

    kb = await repo.get_or_create_knowledge_base(company_id)

    document = await repo.save_document(
        kb_id=kb["kb_id"],
        filename=filename,
        content=content,
        content_type="text/plain",
    )

    success = await process_company_document(
        company_id=company_id,
        document_content=content,
        doc_id=document["doc_id"],
    )
    if not success:
        raise InternalError("Failed to process document")

    return {
        "message": "Text content uploaded and processed successfully",
        "document": document,
        "knowledge_base": kb,
    }


async def list_documents(company_id: str) -> List[Dict[str, Any]]:
    return await repo.get_company_documents(company_id)


async def get_knowledge_base_info(company_id: str) -> Dict[str, Any]:
    return await repo.get_or_create_knowledge_base(company_id)


async def delete_document(doc_id: str, company_id: str) -> Dict[str, str]:
    success = await repo.delete_document(doc_id, company_id)
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
