"""
Chat router — thin HTTP layer for chat messaging endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Dict, Any

from app.auth.dependencies import get_current_user, get_current_company, UserContext
from app.core.exceptions import AppException
from app.features.chat import service
from app.features.chat.schemas import (
    ChatMessageRequest,
    ChatTitleUpdateRequest,
    ChatListResponse,
    ChatHistoryResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _handle(e: AppException):
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/send")
async def send_message(
    data: ChatMessageRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    try:
        chat_id, stream = await service.send_message(
            company_id=user.company_id,
            user_id=user.user_id,
            user_type=user.user_type,
            message=data.message,
            chat_id=data.chat_id,
            chat_title=data.chat_title,
            model=data.model,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@router.get("/history/{chat_id}")
async def get_chat_history(
    chat_id: str,
    user: UserContext = Depends(get_current_user),
) -> ChatHistoryResponse:
    try:
        result = await service.get_chat_history(
            user.company_id, user.user_id, user.user_type, chat_id
        )
        return ChatHistoryResponse(**result)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat history: {str(e)}")


@router.get("/list")
async def list_chats(
    user: UserContext = Depends(get_current_user),
) -> ChatListResponse:
    try:
        result = await service.list_chats(user.company_id, user.user_id, user.user_type)
        return ChatListResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")


@router.put("/title/{chat_id}")
async def update_chat_title(
    chat_id: str,
    data: ChatTitleUpdateRequest,
    user: UserContext = Depends(get_current_user),
):
    try:
        return await service.update_chat_title(
            user.company_id, user.user_id, user.user_type, chat_id, data.title
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat title: {str(e)}")


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user: UserContext = Depends(get_current_user),
):
    try:
        return await service.delete_chat(
            user.company_id, user.user_id, user.user_type, chat_id
        )
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")


@router.post("/setup-knowledge-base")
async def setup_knowledge_base(
    user: UserContext = Depends(get_current_user),
):
    if user.user_type != "company":
        raise HTTPException(status_code=403, detail="Only company users can set up knowledge base")
    return {
        "message": "Knowledge base is automatically set up when you upload documents. "
        "Use /chat/upload-document or /chat/upload-text endpoints to add content."
    }


@router.get("/company-info")
async def get_company_info(
    user: UserContext = Depends(get_current_user),
):
    try:
        return await service.get_company_info(user.company_id)
    except AppException as e:
        _handle(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch company info: {str(e)}")


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "chat"}
