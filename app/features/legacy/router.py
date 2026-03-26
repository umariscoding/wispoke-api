"""
Legacy router — preserves old endpoints for backward compatibility.
These endpoints lack company-scoped auth and should be migrated/removed eventually.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from io import StringIO
from typing import List

from app.services.rag import (
    get_company_rag_chain as get_rag_chain,
    stream_company_response as stream_response,
    clear_cache,
    force_refresh_all_rag_chains,
)
from app.db.operations.chat import (
    update_chat_title,
    fetch_all_chats,
    delete_chat,
    delete_all_chats,
    save_chat,
)
from app.db.operations.message import (
    fetch_messages_old as fetch_messages,
    save_message_old as save_message,
)
from app.models.models import QueryModel

router = APIRouter()


@router.get("/get-all-messages/{chat_id}")
async def get_all_messages(chat_id: str) -> List[dict]:
    return await fetch_messages(chat_id)


@router.get("/get-all-chats")
async def get_all_chats() -> List[dict]:
    return await fetch_all_chats()


@router.post("/edit-chat-title/{chat_id}/{new_title}")
async def edit_chat_title(chat_id: str, new_title: str) -> List[dict]:
    await update_chat_title(chat_id, new_title)
    return [{"message": f"Chat title updated successfully to '{new_title}'."}]


@router.post("/delete-chat/{chat_id}")
async def delete_chat_endpoint(chat_id: str) -> dict:
    await delete_chat(chat_id)
    return {"message": "Chat deleted successfully."}


@router.post("/delete-all-chats/")
async def delete_all_chats_endpoint() -> dict:
    await delete_all_chats()
    return {"message": "All chats deleted successfully."}


@router.post("/save-chat/{chat_id}/{chat_name}")
async def save_chat_endpoint(chat_id: str, chat_name: str) -> dict:
    await save_chat(chat_id, chat_name)
    return {"message": "Chat saved successfully."}


@router.post("/process-txt/")
async def process_txt_file(query_model: QueryModel) -> StreamingResponse:
    try:
        await save_chat(query_model.chat_id, query_model.chat_name)
        await save_message(query_model.chat_id, "human", query_model.question)

        ragchain = get_rag_chain(query_model.model)

        response_buffer = StringIO()

        async def optimized_stream_response(query, chain, chat_id):
            async for chunk in stream_response(query, chain, chat_id):
                response_buffer.write(chunk)
                yield chunk

        async def save_ai_response():
            complete_response = response_buffer.getvalue()
            await save_message(query_model.chat_id, "ai", complete_response)

        async def wrapped_response():
            async for chunk in optimized_stream_response(
                query_model.question, ragchain, query_model.chat_id
            ):
                yield chunk
            await save_ai_response()

        return StreamingResponse(wrapped_response(), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-data/")
async def save_processed_output():
    return {
        "message": "This endpoint is deprecated. Please use /chat/upload-document or /chat/upload-text endpoints for company-specific knowledge base management.",
        "status": "deprecated",
    }


@router.post("/clear-cache/")
async def clear_cache_endpoint():
    try:
        clear_cache()
        return {"message": "Cache cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-refresh-prompts/")
async def force_refresh_prompts_endpoint():
    try:
        force_refresh_all_rag_chains()
        return {"message": "All RAG chains refreshed with updated prompts successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
