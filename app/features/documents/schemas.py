"""Documents feature — request/response schemas."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


class DocumentUploadRequest(BaseModel):
    content: str = Field(..., min_length=1)
    filename: str = Field("document.txt", max_length=255)


class DocumentListResponse(BaseModel):
    documents: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class KnowledgeBaseInfoResponse(BaseModel):
    kb_id: str
    name: str
    description: str = ""
    status: str = "active"
    file_count: int = 0
    created_at: Any = None
    updated_at: Any = None
