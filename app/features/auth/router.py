"""
Auth router — thin HTTP layer. Parses requests, calls service, returns responses.
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.auth import service
from app.features.auth.schemas import (
    CompanyRegisterRequest,
    CompanyLoginRequest,
    RefreshTokenRequest,
    CompanySlugRequest,
    PublishChatbotRequest,
    ChatbotInfoRequest,
    BatchUpdateSettingsRequest,
    EmbedSettingsRequest,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()


@router.post("/company/register")
def register_company(data: CompanyRegisterRequest) -> Dict[str, Any]:
    return service.register_company(data.name, data.email, data.password)


@router.post("/company/login")
def login_company(data: CompanyLoginRequest) -> Dict[str, Any]:
    return service.login_company(data.email, data.password)


@router.get("/company/profile")
async def get_company_profile(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.get_company_profile(current_company.company_id)


@router.post("/refresh")
def refresh_tokens(data: RefreshTokenRequest) -> Dict[str, Any]:
    return service.refresh_tokens(data.refresh_token)


@router.get("/verify")
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    return service.verify_token_info(credentials.credentials)


@router.post("/company/logout")
async def logout_company(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.logout_company(current_company.company_id)


@router.put("/company/slug")
async def update_company_slug(
    data: CompanySlugRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.update_company_slug(current_company.company_id, data.slug)


@router.post("/company/publish-chatbot")
async def publish_chatbot(
    data: PublishChatbotRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.publish_chatbot(current_company.company_id, data.is_published)


@router.put("/company/chatbot-info")
async def update_chatbot_info(
    data: ChatbotInfoRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.update_chatbot_info(
        current_company.company_id, data.chatbot_title, data.chatbot_description
    )


@router.get("/company/chatbot-status")
async def get_chatbot_status(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.get_chatbot_status(current_company.company_id)


@router.get("/company/users")
async def get_company_users(
    page: int = 1,
    page_size: int = 20,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.get_company_users(current_company.company_id, page=page, page_size=page_size)


@router.put("/company/settings")
async def batch_update_settings(
    data: BatchUpdateSettingsRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.batch_update_settings(
        company_id=current_company.company_id,
        slug=data.slug,
        chatbot_title=data.chatbot_title,
        chatbot_description=data.chatbot_description,
        is_published=data.is_published,
        default_model=data.default_model,
        system_prompt=data.system_prompt,
        tone=data.tone,
    )


@router.get("/company/embed-settings")
async def get_embed_settings(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.get_embed_settings(current_company.company_id)


@router.put("/company/embed-settings")
async def update_embed_settings(
    data: EmbedSettingsRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return service.update_embed_settings(
        company_id=current_company.company_id,
        theme=data.theme,
        position=data.position,
        primaryColor=data.primaryColor,
        headerColor=data.headerColor,
        welcomeText=data.welcomeText,
        subtitleText=data.subtitleText,
        placeholderText=data.placeholderText,
        initialMessage=data.initialMessage,
        hideBranding=data.hideBranding,
        autoOpenDelay=data.autoOpenDelay,
        buttonIcon=data.buttonIcon,
        botDisplayName=data.botDisplayName,
        chatTemplate=data.chatTemplate,
    )


@router.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "authentication"}
