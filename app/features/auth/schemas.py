from pydantic import BaseModel
from typing import Optional


class CompanyRegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class CompanyLoginRequest(BaseModel):
    email: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CompanySlugRequest(BaseModel):
    slug: str


class PublishChatbotRequest(BaseModel):
    is_published: bool


class ChatbotInfoRequest(BaseModel):
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None


class BatchUpdateSettingsRequest(BaseModel):
    slug: Optional[str] = None
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None
    is_published: Optional[bool] = None
    default_model: Optional[str] = None
    system_prompt: Optional[str] = None
    tone: Optional[str] = None


class EmbedSettingsRequest(BaseModel):
    theme: Optional[str] = "dark"
    position: Optional[str] = "right"
    primaryColor: Optional[str] = "#6366f1"
    headerColor: Optional[str] = ""
    welcomeText: Optional[str] = "Hi there! How can we help you today?"
    subtitleText: Optional[str] = "We typically reply instantly"
    placeholderText: Optional[str] = "Type your message..."
    initialMessage: Optional[str] = ""
    hideBranding: Optional[bool] = False
    autoOpenDelay: Optional[int] = 0
    buttonIcon: Optional[str] = "chat"
    botDisplayName: Optional[str] = ""
    chatTemplate: Optional[str] = "default"
