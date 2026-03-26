from pydantic import BaseModel
from typing import Optional


class PublicCompanyInfo(BaseModel):
    company_id: str
    name: str
    slug: str
    chatbot_title: str
    chatbot_description: str
    published_at: Optional[str]


class PublicChatMessageRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    model: str = "Llama-large"
