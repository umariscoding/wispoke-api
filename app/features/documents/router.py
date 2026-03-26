"""
Documents router — thin HTTP layer for document and KB management endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import Dict, Any

from app.auth.dependencies import get_current_company, UserContext
from app.core.exceptions import AppException
from app.features.documents import service
from app.features.documents.schemas import (
    DocumentUploadRequest,
    DocumentListResponse,
    KnowledgeBaseInfoResponse,
)

router = APIRouter(prefix="/chat", tags=["documents"])


def _handle(e: AppException):
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_company),
):
    try:
        file_content = await file.read()
        return await service.upload_document(
            company_id=user.company_id,
            file_content=file_content,
            filename=file.filename or "document.txt",
            content_type=file.content_type or "text/plain",
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.post("/upload-text")
async def upload_text_content(
    data: DocumentUploadRequest,
    user: UserContext = Depends(get_current_company),
):
    try:
        return await service.upload_text_content(
            company_id=user.company_id,
            content=data.content,
            filename=data.filename,
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload text content: {str(e)}")


@router.get("/documents")
async def list_documents(
    user: UserContext = Depends(get_current_company),
) -> DocumentListResponse:
    try:
        documents = await service.list_documents(user.company_id)
        return DocumentListResponse(documents=documents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)}")


@router.get("/knowledge-base")
async def get_knowledge_base_info(
    user: UserContext = Depends(get_current_company),
) -> KnowledgeBaseInfoResponse:
    try:
        kb = await service.get_knowledge_base_info(user.company_id)
        return KnowledgeBaseInfoResponse(**kb)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch knowledge base info: {str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    user: UserContext = Depends(get_current_company),
):
    try:
        return await service.delete_document(doc_id, user.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.post("/clear-knowledge-base")
async def clear_knowledge_base(
    user: UserContext = Depends(get_current_company),
):
    try:
        return service.clear_knowledge_base(user.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear knowledge base: {str(e)}")


@router.post("/clear-rag-cache")
async def clear_rag_cache(
    user: UserContext = Depends(get_current_company),
):
    try:
        return service.clear_rag_cache(user.company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear RAG cache: {str(e)}")
