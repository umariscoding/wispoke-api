"""Public feature — request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class PublicCompanyInfo(BaseModel):
    company_id: str
    name: str
    slug: str
    chatbot_title: str
    chatbot_description: str
    published_at: Optional[str] = None


class PublicChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    chat_id: Optional[str] = None
    model: str = "Llama-large"


class PublicEmbedSettingsResponse(BaseModel):
    settings: Dict[str, Any]


class PublicCompanyInfoResponse(BaseModel):
    company_id: str
    name: str
    slug: str
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None
    is_published: bool = False
    published_at: Optional[str] = None
