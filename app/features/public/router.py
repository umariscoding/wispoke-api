"""
Public router — thin HTTP layer for public chatbot endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any

from app.core.exceptions import AppException
from app.features.public import service
from app.features.public.schemas import PublicCompanyInfo, PublicChatMessageRequest

router = APIRouter(prefix="/public", tags=["public"])


def _handle(e: AppException):
    raise HTTPException(status_code=e.status_code, detail=e.message)


# =============================================================================
# SUBDOMAIN-BASED ENDPOINTS
# =============================================================================

@router.get("/")
async def get_subdomain_chatbot_info(request: Request) -> PublicCompanyInfo:
    try:
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        company = await service.get_chatbot_info_by_subdomain(subdomain, is_subdomain_request)
        return PublicCompanyInfo(**company)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chatbot info: {str(e)}")


@router.post("/chat")
async def send_subdomain_message(
    data: PublicChatMessageRequest,
    request: Request,
) -> StreamingResponse:
    try:
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        company = await service.get_chatbot_info_by_subdomain(subdomain, is_subdomain_request)

        chat_id, session_id, stream = await service.send_public_message(
            company=company,
            message=data.message,
            chat_id=data.chat_id,
            model=data.model,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "X-Session-ID": session_id,
                "X-Company-Slug": subdomain,
            },
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process chat message: {str(e)}")


@router.get("/info")
async def get_subdomain_company_info(request: Request) -> Dict[str, Any]:
    try:
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        return await service.get_subdomain_company_info(subdomain, is_subdomain_request)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get company info: {str(e)}")


# =============================================================================
# PATH-BASED ENDPOINTS (BACKWARD COMPATIBILITY)
# =============================================================================

@router.get("/chatbot/{company_slug}")
async def get_public_chatbot_info(company_slug: str) -> PublicCompanyInfo:
    try:
        company = await service.get_chatbot_info_by_slug(company_slug)
        return PublicCompanyInfo(**company)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get chatbot info: {str(e)}")


@router.get("/chatbot/{company_slug}/embed-settings")
async def get_public_embed_settings(company_slug: str) -> Dict[str, Any]:
    try:
        return await service.get_embed_settings(company_slug)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get embed settings: {str(e)}")


@router.post("/chatbot/{company_slug}/chat")
async def send_public_message(
    company_slug: str,
    data: PublicChatMessageRequest,
    request: Request,
) -> StreamingResponse:
    try:
        company = await service.get_chatbot_info_by_slug(company_slug)

        chat_id, session_id, stream = await service.send_public_message(
            company=company,
            message=data.message,
            chat_id=data.chat_id,
            model=data.model,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "X-Session-ID": session_id,
                "X-Company-Slug": company_slug,
            },
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process chat message: {str(e)}")


@router.get("/company/{company_slug}/info")
async def get_public_company_info(company_slug: str) -> Dict[str, Any]:
    try:
        return await service.get_public_company_info(company_slug)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get company info: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "public_chatbot"}
