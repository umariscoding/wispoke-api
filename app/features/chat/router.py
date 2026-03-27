"""
Chat router — thin HTTP layer for chat messaging endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.features.auth.dependencies import get_current_user, UserContext
from app.features.chat import service
from app.features.chat.schemas import (
    ChatMessageRequest,
    ChatTitleUpdateRequest,
    ChatListResponse,
    ChatHistoryResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send")
def send_message(
    data: ChatMessageRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    chat_id, stream = service.send_message(
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


@router.get("/history/{chat_id}")
def get_chat_history(
    chat_id: str,
    page: int = 1,
    page_size: int = 50,
    user: UserContext = Depends(get_current_user),
) -> ChatHistoryResponse:
    result = service.get_chat_history(
        user.company_id, user.user_id, user.user_type, chat_id,
        page=page, page_size=page_size,
    )
    return ChatHistoryResponse(**result)


@router.get("/list")
def list_chats(
    page: int = 1,
    page_size: int = 20,
    user: UserContext = Depends(get_current_user),
) -> ChatListResponse:
    result = service.list_chats(
        user.company_id, user.user_id, user.user_type,
        page=page, page_size=page_size,
    )
    return ChatListResponse(**result)


@router.put("/title/{chat_id}")
def update_chat_title(
    chat_id: str,
    data: ChatTitleUpdateRequest,
    user: UserContext = Depends(get_current_user),
):
    return service.update_chat_title(
        user.company_id, user.user_id, user.user_type, chat_id, data.title
    )


@router.delete("/{chat_id}")
def delete_chat(
    chat_id: str,
    user: UserContext = Depends(get_current_user),
):
    return service.delete_chat(
        user.company_id, user.user_id, user.user_type, chat_id
    )


@router.post("/setup-knowledge-base")
def setup_knowledge_base(
    user: UserContext = Depends(get_current_user),
):
    if user.user_type != "company":
        raise HTTPException(status_code=403, detail="Only company users can set up knowledge base")
    return {
        "message": "Knowledge base is automatically set up when you upload documents. "
        "Use /chat/upload-document or /chat/upload-text endpoints to add content."
    }


@router.get("/company-info")
def get_company_info(
    user: UserContext = Depends(get_current_user),
):
    return service.get_company_info(user.company_id)


@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "chat"}
