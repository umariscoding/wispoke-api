"""
Public router — thin HTTP layer for public chatbot endpoints.
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any

from app.features.public import service
from app.features.public.schemas import PublicCompanyInfo, PublicChatMessageRequest

router = APIRouter(prefix="/public", tags=["public"])


# =============================================================================
# SUBDOMAIN-BASED ENDPOINTS
# =============================================================================

@router.get("/")
def get_subdomain_chatbot_info(request: Request) -> PublicCompanyInfo:
    subdomain = getattr(request.state, "subdomain", None)
    is_subdomain_request = getattr(request.state, "is_subdomain_request", False)
    company = service.get_chatbot_info_by_subdomain(subdomain, is_subdomain_request)
    return PublicCompanyInfo(**company)


@router.post("/chat")
def send_subdomain_message(
    data: PublicChatMessageRequest,
    request: Request,
) -> StreamingResponse:
    subdomain = getattr(request.state, "subdomain", None)
    is_subdomain_request = getattr(request.state, "is_subdomain_request", False)
    company = service.get_chatbot_info_by_subdomain(subdomain, is_subdomain_request)

    chat_id, session_id, stream = service.send_public_message(
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
            "X-Company-Slug": subdomain or "",
        },
    )


@router.get("/info")
def get_subdomain_company_info(request: Request) -> Dict[str, Any]:
    subdomain = getattr(request.state, "subdomain", None)
    is_subdomain_request = getattr(request.state, "is_subdomain_request", False)
    return service.get_subdomain_company_info(subdomain, is_subdomain_request)


# =============================================================================
# PATH-BASED ENDPOINTS (BACKWARD COMPATIBILITY)
# =============================================================================

@router.get("/chatbot/{company_slug}")
def get_public_chatbot_info(company_slug: str) -> PublicCompanyInfo:
    company = service.get_chatbot_info_by_slug(company_slug)
    return PublicCompanyInfo(**company)


@router.get("/chatbot/{company_slug}/embed-settings")
def get_public_embed_settings(company_slug: str) -> Dict[str, Any]:
    return service.get_embed_settings(company_slug)


@router.post("/chatbot/{company_slug}/chat")
def send_public_message(
    company_slug: str,
    data: PublicChatMessageRequest,
    request: Request,
) -> StreamingResponse:
    company = service.get_chatbot_info_by_slug(company_slug)

    chat_id, session_id, stream = service.send_public_message(
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


@router.get("/company/{company_slug}/info")
def get_public_company_info(company_slug: str) -> Dict[str, Any]:
    return service.get_public_company_info(company_slug)


@router.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "public_chatbot"}
