"""
Documents router — thin HTTP layer for document and KB management endpoints.

Mounted at /chat (backward-compatible) with original path structure preserved.
"""

from fastapi import APIRouter, Depends, UploadFile, File

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.billing.dependencies import require_pro_plan
from app.features.documents import service
from app.features.documents.schemas import (
    DocumentUploadRequest,
    DocumentListResponse,
    KnowledgeBaseInfoResponse,
)

router = APIRouter(prefix="/chat", tags=["documents"])


@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_pro_plan),
):
    file_content = await file.read()
    return await service.upload_document(
        company_id=user.company_id,
        file_content=file_content,
        filename=file.filename or "document.txt",
        content_type=file.content_type or "text/plain",
    )


@router.post("/upload-text")
async def upload_text_content(
    data: DocumentUploadRequest,
    user: UserContext = Depends(get_current_company),
):
    from app.services.rag import process_company_document
    from app.features.documents.repository import save_document, get_or_create_knowledge_base
    from app.core.exceptions import ValidationError

    if len(data.content.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValidationError("Content size too large. Maximum 10MB allowed.")

    kb = get_or_create_knowledge_base(user.company_id)
    document = save_document(
        kb_id=kb["kb_id"], filename=data.filename, content=data.content, content_type="text/plain"
    )
    await process_company_document(
        company_id=user.company_id, document_content=data.content, doc_id=document["doc_id"],
        upload_source="text",
    )
    return {
        "message": "Text content uploaded and processed successfully",
        "document": document,
        "knowledge_base": kb,
    }


@router.get("/documents")
def list_documents(
    page: int = 1,
    page_size: int = 20,
    user: UserContext = Depends(get_current_company),
) -> DocumentListResponse:
    result = service.list_documents(user.company_id, page=page, page_size=page_size)
    return DocumentListResponse(**result)


@router.get("/knowledge-base")
def get_knowledge_base_info(
    user: UserContext = Depends(get_current_company),
) -> KnowledgeBaseInfoResponse:
    kb = service.get_knowledge_base_info(user.company_id)
    return KnowledgeBaseInfoResponse(**kb)


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    user: UserContext = Depends(get_current_company),
):
    return service.delete_document(doc_id, user.company_id)


@router.post("/clear-knowledge-base")
def clear_knowledge_base(
    user: UserContext = Depends(get_current_company),
):
    return service.clear_knowledge_base(user.company_id)


@router.post("/clear-rag-cache")
def clear_rag_cache(
    user: UserContext = Depends(get_current_company),
):
    return service.clear_rag_cache(user.company_id)
