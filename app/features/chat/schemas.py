"""Chat feature — request/response schemas."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    chat_id: Optional[str] = None
    chat_title: Optional[str] = Field("New Chat", max_length=200)
    model: str = "Llama-large"


class ChatTitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ChatResponse(BaseModel):
    chat_id: str
    message: str
    response: str
    timestamp: int


class ChatListResponse(BaseModel):
    chats: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
