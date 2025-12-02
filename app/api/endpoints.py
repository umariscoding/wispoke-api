from fastapi import APIRouter, HTTPException
from app.services.langchain_service import create_embeddings_and_store_text, get_pinecone_vectorstore, get_rag_chain, stream_response, clear_cache, force_refresh_all_rag_chains
from app.db.database import (
    update_chat_title,
    fetch_all_chats,
    fetch_messages_old as fetch_messages,
    delete_chat,
    delete_all_chats,
    save_chat,
    save_message_old as save_message,
)
from app.services.document_service import split_text_for_txt
from app.services.fetchdata_service import get_default_no_knowledge_content
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from io import StringIO
from typing import List
from app.models.models import QueryModel

router = APIRouter()

@router.get("/get-all-messages/{chat_id}")
async def get_all_messages(chat_id: str) -> List[dict]:
    """
    Retrieve all messages for a specific chat.
    
    Args:
        chat_id (str): The unique identifier of the chat
        
    Returns:
        List[dict]: A list of message dictionaries containing message details
    """
    return await fetch_messages(chat_id) 

@router.get("/get-all-chats")
async def get_all_chats() -> List[dict]:
    """
    Retrieve all available chats.
    
    Returns:
        List[dict]: A list of chat dictionaries containing chat details
    """
    return await fetch_all_chats()

@router.post("/edit-chat-title/{chat_id}/{new_title}")
async def edit_chat_title(chat_id: str, new_title: str) -> List[dict]:
    """
    Update the title of a specific chat.
    
    Args:
        chat_id (str): The unique identifier of the chat
        new_title (str): The new title to set for the chat
        
    Returns:
        List[dict]: A list containing a success message
    """
    await update_chat_title(chat_id, new_title)
    return [{"message": f"Chat title updated successfully to '{new_title}'."}]

@router.post("/delete-chat/{chat_id}")
async def delete_chat_endpoint(chat_id: str) -> dict:
    """
    Delete a specific chat.
    
    Args:
        chat_id (str): The unique identifier of the chat to delete
        
    Returns:
        dict: A success message confirmation
    """
    await delete_chat(chat_id)
    return {"message": "Chat deleted successfully."}

@router.post("/delete-all-chats/")
async def delete_all_chats_endpoint() -> dict:
    """
    Delete all chats from the system.
    
    Returns:
        dict: A success message confirmation
    """
    await delete_all_chats()
    return {"message": "All chats deleted successfully."}

@router.post("/save-chat/{chat_id}/{chat_name}")
async def save_chat_endpoint(chat_id: str, chat_name: str) -> dict:
    """
    Save a new chat with the specified ID and name.
    
    Args:
        chat_id (str): The unique identifier for the new chat
        chat_name (str): The name of the new chat
        
    Returns:
        dict: A success message confirmation
    """
    await save_chat(chat_id, chat_name)
    return {"message": "Chat saved successfully."} 

@router.post("/process-txt/")
async def process_txt_file(query_model: QueryModel) -> StreamingResponse:
    """
    Process a text query using RAG (Retrieval-Augmented Generation) with optimized caching.
    
    Args:
        query_model (QueryModel): The query model containing chat_id, chat_name, question, and model details
        
    Returns:
        StreamingResponse: A streaming response containing the AI-generated answer
        
    Raises:
        HTTPException: If there's an error during processing
    """
    try:
        # Save chat and human message BEFORE processing RAG chain
        await save_chat(query_model.chat_id, query_model.chat_name)
        await save_message(query_model.chat_id, "human", query_model.question)
        
        # Use cached RAG chain for better performance
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
            async for chunk in optimized_stream_response(query_model.question, ragchain, query_model.chat_id):
                yield chunk
            await save_ai_response()
            
        return StreamingResponse(wrapped_response(), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update-data/")
async def save_processed_output():
    """
    Deprecated endpoint. Use company-specific knowledge base upload endpoints instead.
    
    Returns:
        dict: Deprecation message.
    """
    return {
        "message": "This endpoint is deprecated. Please use /chat/upload-document or /chat/upload-text endpoints for company-specific knowledge base management.",
        "status": "deprecated"
    }

@router.post("/clear-cache/")
async def clear_cache_endpoint():
    """
    Clear all cached objects for performance optimization.
    
    Returns:
        dict: Confirmation message upon successful cache clearing.
    """
    try:
        clear_cache()
        return {"message": "Cache cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/force-refresh-prompts/")
async def force_refresh_prompts_endpoint():
    """
    Force refresh all RAG chains with updated prompts.
    Use this when prompts are updated to ensure all cached chains use the new prompts.
    
    Returns:
        dict: Confirmation message upon successful refresh.
    """
    try:
        force_refresh_all_rag_chains()
        return {"message": "All RAG chains refreshed with updated prompts successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
