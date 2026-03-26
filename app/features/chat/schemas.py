from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ChatMessageRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    chat_title: Optional[str] = "New Chat"
    model: str = "Llama-large"


class ChatTitleUpdateRequest(BaseModel):
    title: str


class ChatResponse(BaseModel):
    chat_id: str
    message: str
    response: str
    timestamp: int


class ChatListResponse(BaseModel):
    chats: List[Dict[str, Any]]


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]]
