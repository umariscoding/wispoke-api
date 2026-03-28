"""Auth feature — request/response schemas with validation."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class CompanyRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class CompanyLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CompanySlugRequest(BaseModel):
    slug: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9\-_]+$")


class PublishChatbotRequest(BaseModel):
    is_published: bool


class ChatbotInfoRequest(BaseModel):
    chatbot_title: Optional[str] = Field(None, max_length=200)
    chatbot_description: Optional[str] = Field(None, max_length=2000)


class BatchUpdateSettingsRequest(BaseModel):
    slug: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-z0-9\-]+$")
    chatbot_title: Optional[str] = Field(None, max_length=200)
    chatbot_description: Optional[str] = Field(None, max_length=2000)
    is_published: Optional[bool] = None
    default_model: Optional[str] = None
    system_prompt: Optional[str] = Field(None, max_length=5000)
    tone: Optional[str] = None
    enable_user_portal: Optional[bool] = None


class EmbedSettingsRequest(BaseModel):
    theme: Optional[str] = "dark"
    position: Optional[str] = "right"
    primaryColor: Optional[str] = Field("#6366f1", max_length=20)
    headerColor: Optional[str] = Field("", max_length=20)
    welcomeText: Optional[str] = Field("Hi there! How can we help you today?", max_length=500)
    subtitleText: Optional[str] = Field("We typically reply instantly", max_length=500)
    placeholderText: Optional[str] = Field("Type your message...", max_length=200)
    showHeaderSubtitle: Optional[bool] = True
    hideBranding: Optional[bool] = False
    autoOpenDelay: Optional[int] = Field(0, ge=0, le=60)
    buttonIcon: Optional[str] = Field("chat", max_length=50)
    chatTemplate: Optional[str] = Field("default", max_length=50)
    suggestedMessages: Optional[List[str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class TokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CompanyResponse(BaseModel):
    company_id: str
    name: str
    slug: Optional[str] = None
    email: Optional[str] = None


class CompanyRegisterResponse(BaseModel):
    message: str
    company: Dict[str, Any]
    tokens: TokensResponse


class CompanyLoginResponse(BaseModel):
    message: str
    company: Dict[str, Any]
    tokens: TokensResponse


class CompanyProfileResponse(BaseModel):
    company: Dict[str, Any]


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyTokenResponse(BaseModel):
    valid: bool
    user_info: Dict[str, Any]


class MessageResponse(BaseModel):
    message: str


class ChatbotStatusResponse(BaseModel):
    company_id: str
    slug: Optional[str] = None
    is_published: bool
    published_at: Optional[str] = None
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None
    public_url: Optional[str] = None


class CompanyUsersListResponse(BaseModel):
    company_id: str
    company_name: str
    users: List[Dict[str, Any]]
    total_users: int
    page: int
    page_size: int
    total_pages: int


class SettingsUpdateResponse(BaseModel):
    message: str
    company: Dict[str, Any]


class EmbedSettingsResponse(BaseModel):
    settings: Dict[str, Any]
