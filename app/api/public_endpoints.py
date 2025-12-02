"""
Public chatbot endpoints for accessing published chatbots without authentication
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.models.models import PublicChatMessage
from app.db.operations.company import (
    get_published_company_info,
    get_company_by_slug
)
from app.db.operations.guest import create_guest_session
from app.db.operations.chat import create_chat, get_chat_by_id
from app.db.operations.message import save_message
from app.services.rag import (
    stream_company_response,
    get_company_vector_store,
    
)
# from app.services.fetchdata_service import get_default_no_knowledge_content
# from app.services.document_processing import split_text_for_txt
import uuid
import json
import asyncio

router = APIRouter(prefix="/public", tags=["public"])

class PublicCompanyInfo(BaseModel):
    company_id: str
    name: str
    slug: str
    chatbot_title: str
    chatbot_description: str
    published_at: Optional[str]

# =============================================================================
# SUBDOMAIN-BASED ENDPOINTS (NEW APPROACH)
# =============================================================================

@router.get("/")
async def get_subdomain_chatbot_info(request: Request) -> PublicCompanyInfo:
    """
    Get public chatbot information via subdomain (e.g., kfcchatbot.mysite.com)
    
    This endpoint works when accessed via subdomain routing.
    Example: kfcchatbot.mysite.com/ → shows KFC chatbot info
    
    Returns:
        PublicCompanyInfo: Public chatbot information
        
    Raises:
        HTTPException: If chatbot not found or not published
    """
    try:
        # Get subdomain from middleware
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        
        if not is_subdomain_request or not subdomain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found. Please check the URL."
            )
        
        # Get company by slug (subdomain)
        company = await get_published_company_info(subdomain)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found or not published"
            )
        
        return PublicCompanyInfo(**company)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chatbot info: {str(e)}"
        )

@router.post("/chat")
async def send_subdomain_message(
    message_data: PublicChatMessage,
    request: Request
) -> StreamingResponse:
    """
    Send a message to a subdomain-based public chatbot.
    
    This endpoint works when accessed via subdomain routing.
    Example: POST to kfcchatbot.mysite.com/chat
    
    Args:
        message_data: Chat message data
        request: FastAPI request object (contains subdomain info)
        
    Returns:
        StreamingResponse: Server-sent events stream with AI response
        
    Raises:
        HTTPException: If chatbot not found or chat fails
    """
    try:
        # Get subdomain from middleware
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        
        if not is_subdomain_request or not subdomain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found. Please check the URL."
            )
        
        # Verify chatbot is published
        company = await get_published_company_info(subdomain)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found or not published"
            )
        
        # Generate chat_id if not provided
        chat_id = message_data.chat_id or str(uuid.uuid4())

        # Check if chat already exists
        existing_chat = await get_chat_by_id(chat_id)

        # Only create guest session and chat if chat doesn't exist
        if not existing_chat:
            # Create guest session for this company
            guest_session = await create_guest_session(
                company_id=company["company_id"],
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )

            # Create new chat
            await create_chat(
                company_id=company["company_id"],
                chat_id=chat_id,
                title="Public Chat",
                session_id=guest_session["session_id"]
            )
        else:
            # Chat exists, use existing session_id for response headers
            guest_session = {"session_id": existing_chat.get("session_id", "")}
        
        await save_message(
            company_id=company["company_id"],
            chat_id=chat_id,
            role="human",
            content=message_data.message
        )
        
        # Set up response streaming
        async def stream_and_save():
            try:
                # Send initial metadata
                yield f"data: {json.dumps({'chat_id': chat_id, 'session_id': guest_session['session_id'], 'type': 'start'})}\n\n"
                
                # Stream AI response
                response_buffer = []
                async for chunk in stream_company_response(
                    company_id=company["company_id"],
                    query=message_data.message,
                    chat_id=chat_id,
                    llm_model=message_data.model
                ):
                    response_buffer.append(chunk)
                    escaped_chunk = chunk.replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
                    yield f"data: {json.dumps({'content': escaped_chunk, 'type': 'chunk'})}\n\n"
                
                # Send completion signal
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                
                # Save complete AI response
                complete_response = ''.join(response_buffer)
                await save_message(
                    company_id=company["company_id"],
                    chat_id=chat_id,
                    role="ai",
                    content=complete_response
                )
                
            except Exception as e:
                error_msg = str(e).replace('"', '\\"')
                yield f"data: {json.dumps({'error': error_msg, 'type': 'error'})}\n\n"
        
        return StreamingResponse(
            stream_and_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "X-Session-ID": guest_session["session_id"],
                "X-Company-Slug": subdomain
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat message: {str(e)}"
        )

@router.get("/info")
async def get_subdomain_company_info(request: Request) -> Dict[str, Any]:
    """
    Get public company information via subdomain.
    
    This endpoint works when accessed via subdomain routing.
    Example: kfcchatbot.mysite.com/info → shows KFC company info
    
    Args:
        request: FastAPI request object (contains subdomain info)
        
    Returns:
        Dict containing public company information
        
    Raises:
        HTTPException: If company not found
    """
    try:
        # Get subdomain from middleware
        subdomain = getattr(request.state, 'subdomain', None)
        is_subdomain_request = getattr(request.state, 'is_subdomain_request', False)
        
        if not is_subdomain_request or not subdomain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found. Please check the URL."
            )
        
        # Get company by slug (subdomain)
        company = await get_company_by_slug(subdomain)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        return {
            "company_id": company["company_id"],
            "name": company["name"],
            "slug": company["slug"],
            "chatbot_title": company.get("chatbot_title"),
            "chatbot_description": company.get("chatbot_description"),
            "is_published": company.get("is_published", False),
            "published_at": company.get("published_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company info: {str(e)}"
        )

# =============================================================================
# ORIGINAL PATH-BASED ENDPOINTS (BACKWARD COMPATIBILITY)
# =============================================================================

@router.get("/chatbot/{company_slug}")
async def get_public_chatbot_info(company_slug: str) -> PublicCompanyInfo:
    """
    Get public chatbot information by company slug.
    
    Args:
        company_slug: Company slug
        
    Returns:
        PublicCompanyInfo: Public chatbot information
        
    Raises:
        HTTPException: If chatbot not found or not published
    """
    try:
        company = await get_published_company_info(company_slug)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found or not published"
            )
        
        return PublicCompanyInfo(**company)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chatbot info: {str(e)}"
        )

@router.post("/chatbot/{company_slug}/chat")
async def send_public_message(
    company_slug: str,
    message_data: PublicChatMessage,
    request: Request
) -> StreamingResponse:
    """
    Send a message to a public chatbot and receive streaming response.
    
    Args:
        company_slug: Company slug
        message_data: Chat message data
        request: FastAPI request object
        
    Returns:
        StreamingResponse: Server-sent events stream with AI response
        
    Raises:
        HTTPException: If chatbot not found or chat fails
    """
    try:
        # Verify chatbot is published
        company = await get_published_company_info(company_slug)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chatbot not found or not published"
            )
        
        company_id = company["company_id"]

        # Generate chat_id if not provided
        chat_id = message_data.chat_id or str(uuid.uuid4())

        # Check if chat already exists
        existing_chat = await get_chat_by_id(chat_id)

        # Only create guest session and chat if chat doesn't exist
        if not existing_chat:
            # Create guest session for this company
            guest_session = await create_guest_session(
                company_id=company_id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )

            # Create new chat
            await create_chat(
                company_id=company_id,
                chat_id=chat_id,
                title="Public Chat",
                session_id=guest_session["session_id"]
            )
        else:
            # Chat exists, use existing session_id for response headers
            guest_session = {"session_id": existing_chat.get("session_id", "")}
        
        await save_message(
            company_id=company_id,
            chat_id=chat_id,
            role="human",
            content=message_data.message
        )
        
        # Set up response streaming
        async def stream_and_save():
            try:
                # Send initial metadata
                yield f"data: {json.dumps({'chat_id': chat_id, 'session_id': guest_session['session_id'], 'type': 'start'})}\n\n"
                
                # Stream AI response
                response_buffer = []
                async for chunk in stream_company_response(
                    company_id=company_id,
                    query=message_data.message,
                    chat_id=chat_id,
                    llm_model=message_data.model
                ):
                    response_buffer.append(chunk)
                    escaped_chunk = chunk.replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
                    chunk_data = {'content': escaped_chunk, 'type': 'chunk'}
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                
                # Send completion signal
                end_data = {'type': 'end'}
                yield f"data: {json.dumps(end_data)}\n\n"
                
                # Save complete AI response
                complete_response = ''.join(response_buffer)
                await save_message(
                    company_id=company_id,
                    chat_id=chat_id,
                    role="ai",
                    content=complete_response
                )
                
            except Exception as e:
                error_msg = str(e).replace('"', '\\"')
                error_data = {'error': error_msg, 'type': 'error'}
                yield f"data: {json.dumps(error_data)}\n\n"
        return StreamingResponse(
            stream_and_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "X-Session-ID": guest_session["session_id"],
                "X-Company-Slug": company_slug
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat message: {str(e)}"
        )

@router.get("/company/{company_slug}/info")
async def get_public_company_info(company_slug: str) -> Dict[str, Any]:
    """
    Get basic public information about a company.
    
    Args:
        company_slug: Company slug
        
    Returns:
        Dict containing public company information
        
    Raises:
        HTTPException: If company not found
    """
    try:
        company = await get_company_by_slug(company_slug)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        return {
            "company_id": company["company_id"],
            "name": company["name"],
            "slug": company["slug"],
            "chatbot_title": company.get("chatbot_title"),
            "chatbot_description": company.get("chatbot_description"),
            "is_published": company.get("is_published", False),
            "published_at": company.get("published_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company info: {str(e)}"
        )

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for public chatbot service.
    
    Returns:
        Dict containing health status
    """
    return {
        "status": "healthy",
        "service": "public_chatbot"
    }

async def ensure_company_knowledge_base(company_id: str):
    """
    Ensure knowledge base is set up for a company.
    If not exists, create it with dummy data.
    """
    try:
        # Try to get existing vector store
        vector_store = get_company_vector_store(company_id)
        
        # Test if vector store has any data by attempting a simple search
        retriever = vector_store.as_retriever(search_kwargs={"k": 1})
        docs = retriever.invoke("test query")
        
        # If no documents found, set up default knowledge base
        if not docs:
            content = get_default_no_knowledge_content()
            doc_chunks = split_text_for_txt(content)
            setup_company_knowledge_base(company_id, doc_chunks)
            
    except Exception as e:
        # If any error occurs, set up default knowledge base
        content = get_default_no_knowledge_content()
        doc_chunks = split_text_for_txt(content)
        setup_company_knowledge_base(company_id, doc_chunks) 