from pydantic import BaseModel
from typing import List, Dict, Any


class DocumentUploadRequest(BaseModel):
    content: str
    filename: str = "document.txt"


class DocumentListResponse(BaseModel):
    documents: List[Dict[str, Any]]


class KnowledgeBaseInfoResponse(BaseModel):
    kb_id: str
    name: str
    description: str
    status: str
    file_count: int
    created_at: Any
    updated_at: Any
