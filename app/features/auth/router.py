"""
Auth router — thin HTTP layer. Parses requests, calls service, returns responses.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any

from app.auth.dependencies import get_current_company, UserContext
from app.core.exceptions import AppException
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


def _handle(e: AppException):
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/company/register")
async def register_company(data: CompanyRegisterRequest) -> Dict[str, Any]:
    try:
        return await service.register_company(data.name, data.email, data.password)
    except AppException as e:
        _handle(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/company/login")
async def login_company(data: CompanyLoginRequest) -> Dict[str, Any]:
    try:
        return await service.login_company(data.email, data.password)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.get("/company/profile")
async def get_company_profile(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.get_company_profile(current_company.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")


@router.post("/refresh")
async def refresh_tokens(data: RefreshTokenRequest) -> Dict[str, Any]:
    try:
        return await service.refresh_tokens(data.refresh_token)
    except AppException as e:
        _handle(e)
    except Exception as e:
        error_message = str(e)
        if any(kw in error_message.lower() for kw in ("signature", "invalid", "decode")):
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {error_message}")


@router.get("/verify")
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    try:
        return await service.verify_token_info(credentials.credentials)
    except AppException as e:
        _handle(e)
    except Exception as e:
        error_message = str(e)
        if any(kw in error_message.lower() for kw in ("signature", "invalid", "decode")):
            raise HTTPException(status_code=401, detail="Invalid token signature")
        raise HTTPException(status_code=500, detail=f"Token verification failed: {error_message}")


@router.post("/company/logout")
async def logout_company(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    return await service.logout_company(current_company.company_id)


@router.put("/company/slug")
async def update_company_slug(
    data: CompanySlugRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.update_company_slug(current_company.company_id, data.slug)
    except AppException as e:
        _handle(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update slug: {str(e)}")


@router.post("/company/publish-chatbot")
async def publish_chatbot(
    data: PublishChatbotRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.publish_chatbot(current_company.company_id, data.is_published)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish chatbot: {str(e)}")


@router.put("/company/chatbot-info")
async def update_chatbot_info(
    data: ChatbotInfoRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.update_chatbot_info(
            current_company.company_id, data.chatbot_title, data.chatbot_description
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chatbot info: {str(e)}")


@router.get("/company/chatbot-status")
async def get_chatbot_status(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.get_chatbot_status(current_company.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chatbot status: {str(e)}")


@router.get("/company/users")
async def get_company_users(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.get_company_users(current_company.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get company users: {str(e)}")


@router.put("/company/settings")
async def batch_update_settings(
    data: BatchUpdateSettingsRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.batch_update_settings(
            company_id=current_company.company_id,
            slug=data.slug,
            chatbot_title=data.chatbot_title,
            chatbot_description=data.chatbot_description,
            is_published=data.is_published,
            default_model=data.default_model,
            system_prompt=data.system_prompt,
            tone=data.tone,
        )
    except AppException as e:
        _handle(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")


@router.get("/company/embed-settings")
async def get_embed_settings(
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.get_embed_settings(current_company.company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get embed settings: {str(e)}")


@router.put("/company/embed-settings")
async def update_embed_settings(
    data: EmbedSettingsRequest,
    current_company: UserContext = Depends(get_current_company),
) -> Dict[str, Any]:
    try:
        return await service.update_embed_settings(
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
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update embed settings: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "authentication"}
