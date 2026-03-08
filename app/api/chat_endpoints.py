from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from io import StringIO
import uuid
import json

from app.auth.dependencies import get_current_user, get_current_company, UserContext
from app.services.rag import (
    get_company_rag_chain,
    stream_company_response,
    get_company_vector_store,
    process_company_document,
    clear_company_knowledge_base,
    clear_company_cache,
    get_pinecone_client,
    get_company_index_name
)
from app.services.document_processing import (
    split_text_for_txt,
    validate_file_type,
    extract_text_from_file,
    upload_file_to_supabase
)
from app.db.operations.chat import (
    create_chat,
    get_chat_by_id,
    fetch_company_chats,
    update_chat_title,
    delete_chat
)
from app.db.operations.message import save_message, fetch_messages
from app.db.operations.company import get_company_by_id
from app.db.operations.knowledge_base import get_or_create_knowledge_base
from app.db.operations.document import (
    save_document,
    get_company_documents,
    delete_document
)
from app.db.operations.client import generate_id, db

router = APIRouter(prefix="/chat", tags=["chat"])

def safe_json_dumps(data):
    """Safely serialize data to JSON with proper escaping"""
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))

# Pydantic models
class ChatMessage(BaseModel):
    message: str
    chat_id: Optional[str] = None
    chat_title: Optional[str] = "New Chat"
    model: str = "Llama-instant"  # Options: Llama-instant, Llama-large, OpenAI, Claude, Cohere

class ChatTitleUpdate(BaseModel):
    title: str

class ChatResponse(BaseModel):
    chat_id: str
    message: str
    response: str
    timestamp: int

class ChatList(BaseModel):
    chats: List[Dict[str, Any]]

class ChatHistory(BaseModel):
    messages: List[Dict[str, Any]]

class DocumentUpload(BaseModel):
    content: str
    filename: str = "document.txt"

class DocumentList(BaseModel):
    documents: List[Dict[str, Any]]

class KnowledgeBaseInfo(BaseModel):
    kb_id: str
    name: str
    description: str
    status: str
    file_count: int
    created_at: Any
    updated_at: Any

@router.post("/send")
async def send_message(
    message_data: ChatMessage,
    user: UserContext = Depends(get_current_user)
) -> StreamingResponse:
    """
    Send a message to the chatbot and get a streaming response.
    Works for both registered users and guest sessions.
    """
    try:
        # Ensure company knowledge base is set up
        await ensure_company_knowledge_base(user.company_id)
        
        # Generate chat_id if not provided
        chat_id = message_data.chat_id or str(uuid.uuid4())

        # Check if chat already exists
        existing_chat = await get_chat_by_id(chat_id)

        # Only create chat if it doesn't exist
        if not existing_chat:
            # Determine user_id and session_id based on user type
            user_id = user.user_id if user.user_type == "user" else None
            session_id = user.user_id if user.user_type == "guest" else None  # For guests, user_id is session_id

            # Create new chat
            await create_chat(
                company_id=user.company_id,
                chat_id=chat_id,
                title=message_data.chat_title or "New Chat",
                user_id=user_id,
                session_id=session_id
            )
        
        await save_message(
            company_id=user.company_id,
            chat_id=chat_id,
            role="human",
            content=message_data.message
        )
        
        # Set up response buffering for saving
        response_buffer = StringIO()
        
        async def stream_and_save():
            """Stream response and save to database"""
            try:
                # Add chat_id to response headers
                async def generate_response():
                    try:
                        # Send start message with proper JSON
                        start_data = {"chat_id": chat_id, "type": "start"}
                        yield f"data: {safe_json_dumps(start_data)}\n\n"
                        
                        async for chunk in stream_company_response(
                            company_id=user.company_id,
                            query=message_data.message,
                            chat_id=chat_id,
                            llm_model=message_data.model
                        ):
                            response_buffer.write(chunk)
                            # Clean chunk and ensure proper JSON escaping
                            clean_chunk = chunk.replace(chr(10), ' ').replace(chr(13), ' ')
                            chunk_data = {"content": clean_chunk, "type": "chunk"}
                            yield f"data: {safe_json_dumps(chunk_data)}\n\n"
                        
                        # Send end message with proper JSON
                        end_data = {"type": "end"}
                        yield f"data: {safe_json_dumps(end_data)}\n\n"
                        
                    except Exception as stream_error:
                        # Handle streaming errors gracefully
                        error_msg = str(stream_error)
                        if "LocalProtocolError" not in error_msg and "Can't send data" not in error_msg:
                            error_data = {"error": error_msg, "type": "error"}
                            yield f"data: {safe_json_dumps(error_data)}\n\n"
                        # For protocol errors, just log and continue - response was likely sent
                        
                    finally:
                        # Always try to save the response, even if streaming failed
                        try:
                            complete_response = response_buffer.getvalue()
                            if complete_response.strip():  # Only save non-empty responses
                                await save_message(
                                    company_id=user.company_id,
                                    chat_id=chat_id,
                                    role="ai",
                                    content=complete_response
                                )
                        except Exception:
                            pass  # Don't let save errors affect the response
                
                async for chunk in generate_response():
                    yield chunk
                    
            except Exception as e:
                # Handle any outer exceptions
                error_msg = str(e)
                if "LocalProtocolError" not in error_msg and "Can't send data" not in error_msg:
                    error_data = {"error": error_msg, "type": "error"}
                    yield f"data: {safe_json_dumps(error_data)}\n\n"
        
        return StreamingResponse(
            stream_and_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Chat-ID": chat_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "X-Accel-Buffering": "no"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@router.get("/history/{chat_id}")
async def get_chat_history(
    chat_id: str,
    user: UserContext = Depends(get_current_user)
) -> ChatHistory:
    """
    Get chat history for a specific chat.
    Only accessible by users/guests belonging to the same company.
    """
    try:
        # Fetch messages for this company and chat
        messages = fetch_messages(user.company_id, chat_id)

        # Additional access control: verify the chat belongs to this user/session
        chats = await fetch_company_chats(
            company_id=user.company_id,
            user_id=user.user_id if user.user_type == "user" else None,
            session_id=user.user_id if user.user_type == "guest" else None
        )

        # Check if this chat belongs to the user
        chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
        if not chat_exists:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")

        return ChatHistory(messages=messages)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat history: {str(e)}")

@router.get("/list")
async def list_chats(
    user: UserContext = Depends(get_current_user)
) -> ChatList:
    """
    List all chats for the current user/guest session.
    Only shows chats belonging to the same company.
    """
    try:
        # Determine user_id and session_id based on user type
        user_id = user.user_id if user.user_type == "user" else None
        session_id = user.user_id if user.user_type == "guest" else None
        
        # Fetch chats for this company and user
        chats = await fetch_company_chats(
            company_id=user.company_id,
            user_id=user_id,
            session_id=session_id
        )
        
        return ChatList(chats=chats)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")

@router.put("/title/{chat_id}")
async def update_chat_title_endpoint(
    chat_id: str,
    title_data: ChatTitleUpdate,
    user: UserContext = Depends(get_current_user)
):
    """
    Update the title of a chat.
    Only accessible by the owner of the chat.
    """
    try:
        # Verify the chat belongs to this user
        chats = await fetch_company_chats(
            company_id=user.company_id,
            user_id=user.user_id if user.user_type == "user" else None,
            session_id=user.user_id if user.user_type == "guest" else None
        )
        
        chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
        if not chat_exists:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        
        # Update the chat title
        await update_chat_title(user.company_id, chat_id, title_data.title)
        
        return {"message": "Chat title updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat title: {str(e)}")

@router.delete("/{chat_id}")
async def delete_chat_endpoint(
    chat_id: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Delete a chat.
    Only accessible by the owner of the chat.
    """
    try:
        # Verify the chat belongs to this user
        chats = await fetch_company_chats(
            company_id=user.company_id,
            user_id=user.user_id if user.user_type == "user" else None,
            session_id=user.user_id if user.user_type == "guest" else None
        )
        
        chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
        if not chat_exists:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        
        # Delete the chat
        await delete_chat(user.company_id, chat_id)
        
        return {"message": "Chat deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")

@router.post("/setup-knowledge-base")
async def setup_knowledge_base(
    user: UserContext = Depends(get_current_user)
):
    """
    Set up the knowledge base for a company.
    Only accessible by company users (not guests).
    """
    try:
        # Only company users can set up knowledge base
        if user.user_type != "company":
            raise HTTPException(status_code=403, detail="Only company users can set up knowledge base")
        
        # Knowledge base is now set up automatically when documents are uploaded
        # This endpoint is deprecated - use /chat/upload-document or /chat/upload-text instead
        return {"message": "Knowledge base is automatically set up when you upload documents. Use /chat/upload-document or /chat/upload-text endpoints to add content."}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set up knowledge base: {str(e)}")

@router.get("/company-info")
async def get_company_info(
    user: UserContext = Depends(get_current_user)
):
    """
    Get information about the current company.
    """
    try:
        company = await get_company_by_id(user.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        
        return {
            "company": {
                "company_id": company["company_id"],
                "name": company["name"],
                "plan": company["plan"],
                "status": company["status"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch company info: {str(e)}")

@router.get("/health")
async def health_check():
    """
    Health check endpoint for chat service.
    """
    return {"status": "healthy", "service": "chat"}

@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_company)
):
    """
    Upload a document (PDF, TXT, or DOCX) to the company's knowledge base.
    Only accessible by company users.
    """
    try:
        # Validate file type
        if not validate_file_type(file.filename or "", file.content_type or ""):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Only PDF, TXT, and DOCX files are supported."
            )

        # Validate file size (max 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum 10MB allowed."
            )

        # Get or create knowledge base
        kb = await get_or_create_knowledge_base(user.company_id)

        # Generate document ID first (needed for file path)
        doc_id = generate_id()

        # Upload file to Supabase storage
        try:
            file_url = await upload_file_to_supabase(
                file_content=file_content,
                filename=file.filename or "document.txt",
                company_id=user.company_id,
                doc_id=doc_id
            )
        except Exception as upload_error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload file to storage: {str(upload_error)}"
            )

        # Extract text content from file
        try:
            text_content = await extract_text_from_file(
                file_content=file_content,
                filename=file.filename or "document.txt",
                content_type=file.content_type or "text/plain"
            )
        except Exception as extract_error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract text from file: {str(extract_error)}"
            )

        # Save document to database with file URL
        document = await save_document(
            kb_id=kb["kb_id"],
            filename=file.filename or "document.txt",
            content=text_content,
            content_type=file.content_type or "text/plain",
            file_url=file_url
        )

        # Update the document with the generated doc_id
        db.table("documents").update({"doc_id": doc_id}).eq("doc_id", document["doc_id"]).execute()
        document["doc_id"] = doc_id

        # Process document in background
        success = await process_company_document(
            company_id=user.company_id,
            document_content=text_content,
            doc_id=doc_id
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to process document"
            )

        return {
            "message": "Document uploaded and processed successfully",
            "document": {
                **document,
                "file_url": file_url
            },
            "knowledge_base": kb
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload document: {str(e)}"
        )

@router.post("/upload-text")
async def upload_text_content(
    document_data: DocumentUpload,
    user: UserContext = Depends(get_current_company)
):
    """
    Upload text content directly to the company's knowledge base.
    Only accessible by company users.
    """
    try:
        # Validate content size (max 10MB)
        if len(document_data.content.encode('utf-8')) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Content size too large. Maximum 10MB allowed."
            )
        
        # Get or create knowledge base
        kb = await get_or_create_knowledge_base(user.company_id)
        
        # Save document to database
        document = await save_document(
            kb_id=kb["kb_id"],
            filename=document_data.filename,
            content=document_data.content,
            content_type="text/plain"
        )
        
        # Process document
        success = await process_company_document(
            company_id=user.company_id,
            document_content=document_data.content,
            doc_id=document["doc_id"]
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to process document"
            )
        
        return {
            "message": "Text content uploaded and processed successfully",
            "document": document,
            "knowledge_base": kb
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload text content: {str(e)}"
        )

@router.get("/documents")
async def list_documents(
    user: UserContext = Depends(get_current_company)
) -> DocumentList:
    """
    List all documents in the company's knowledge base.
    Only accessible by company users.
    """
    try:
        documents = await get_company_documents(user.company_id)
        return DocumentList(documents=documents)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch documents: {str(e)}"
        )

@router.get("/knowledge-base")
async def get_knowledge_base_info(
    user: UserContext = Depends(get_current_company)
) -> KnowledgeBaseInfo:
    """
    Get knowledge base information for the company.
    Only accessible by company users.
    """
    try:
        kb = await get_or_create_knowledge_base(user.company_id)
        return KnowledgeBaseInfo(**kb)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch knowledge base info: {str(e)}"
        )

@router.delete("/documents/{doc_id}")
async def delete_document_endpoint(
    doc_id: str,
    user: UserContext = Depends(get_current_company)
):
    """
    Delete a document from the company's knowledge base.
    Only accessible by company users.
    """
    try:
        success = await delete_document(doc_id, user.company_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
            )
        
        return {"message": "Document deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )

@router.post("/clear-knowledge-base")
async def clear_knowledge_base(
    user: UserContext = Depends(get_current_company)
):
    """
    Clear all content from the company's knowledge base.
    Only accessible by company users.
    """
    try:
        success = clear_company_knowledge_base(user.company_id)
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to clear knowledge base"
            )
        
        return {"message": "Knowledge base cleared successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear knowledge base: {str(e)}"
        )

@router.post("/clear-rag-cache")
async def clear_rag_cache(
    user: UserContext = Depends(get_current_company)
):
    """
    Clear the RAG chain cache for the current company.
    This will force the system to rebuild the RAG chain with updated prompts.
    Only accessible by company users.
    """
    try:
        clear_company_cache(user.company_id)
        return {"message": "RAG cache cleared successfully. New prompts will take effect on next chat message."}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear RAG cache: {str(e)}"
        )

# Helper functions
async def ensure_company_knowledge_base(company_id: str):
    """
    Ensure knowledge base is set up for a company.
    Each company has their own dedicated Pinecone index.
    """
    try:
        # Check if company's Pinecone index exists and has vectors
        index_name = get_company_index_name(company_id)
        pc = get_pinecone_client()

        # Check if index exists
        existing_indexes = [idx["name"] for idx in pc.list_indexes()]

        if index_name not in existing_indexes:
            # No index exists - company should upload documents
            return

        # Check if index has vectors
        index = pc.Index(index_name)
        stats = index.describe_index_stats()

        has_vectors = stats.total_vector_count > 0

        if has_vectors:
            # Clear any stale cache to ensure fresh connections
            clear_company_cache(company_id)
            return

        # No vectors found - company should upload documents
        return

    except Exception:
        # If any error occurs, preserve existing content
        return 