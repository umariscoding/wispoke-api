"""
Chat service — business logic for chat messaging, history, and management.
No HTTP concepts. Raises domain exceptions.
"""

import uuid
import json
from io import StringIO
from typing import Dict, Any, List, AsyncGenerator

from app.core.exceptions import NotFoundError
from app.services.rag import (
    stream_company_response,
    get_pinecone_client,
    get_company_index_name,
    clear_company_cache,
)
from app.features.chat import repository as repo


def safe_json_dumps(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


async def ensure_company_knowledge_base(company_id: str):
    try:
        index_name = get_company_index_name(company_id)
        pc = get_pinecone_client()
        existing_indexes = [idx["name"] for idx in pc.list_indexes()]
        if index_name not in existing_indexes:
            return
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        has_vectors = stats.total_vector_count > 0
        if has_vectors:
            clear_company_cache(company_id)
            return
        return
    except Exception:
        return


async def send_message(
    company_id: str,
    user_id: str,
    user_type: str,
    message: str,
    chat_id: str = None,
    chat_title: str = "New Chat",
    model: str = "Llama-large",
) -> tuple:
    """
    Orchestrate sending a message: ensure KB, create chat if needed, save message.
    Returns (chat_id, stream_generator) for the router to wrap in StreamingResponse.
    """
    await ensure_company_knowledge_base(company_id)

    chat_id = chat_id or str(uuid.uuid4())
    existing_chat = await repo.get_chat_by_id(chat_id)

    if not existing_chat:
        msg_user_id = user_id if user_type == "user" else None
        session_id = user_id if user_type == "guest" else None
        await repo.create_chat(
            company_id=company_id,
            chat_id=chat_id,
            title=chat_title,
            user_id=msg_user_id,
            session_id=session_id,
        )

    await repo.save_message(
        company_id=company_id, chat_id=chat_id, role="human", content=message
    )

    response_buffer = StringIO()

    async def stream_and_save():
        try:
            async def generate_response():
                try:
                    start_data = {"chat_id": chat_id, "type": "start"}
                    yield f"data: {safe_json_dumps(start_data)}\n\n"

                    async for chunk in stream_company_response(
                        company_id=company_id,
                        query=message,
                        chat_id=chat_id,
                        llm_model=model,
                    ):
                        response_buffer.write(chunk)
                        clean_chunk = chunk.replace(chr(10), ' ').replace(chr(13), ' ')
                        chunk_data = {"content": clean_chunk, "type": "chunk"}
                        yield f"data: {safe_json_dumps(chunk_data)}\n\n"

                    end_data = {"type": "end"}
                    yield f"data: {safe_json_dumps(end_data)}\n\n"

                except Exception as stream_error:
                    error_msg = str(stream_error)
                    if "LocalProtocolError" not in error_msg and "Can't send data" not in error_msg:
                        error_data = {"error": error_msg, "type": "error"}
                        yield f"data: {safe_json_dumps(error_data)}\n\n"

                finally:
                    try:
                        complete_response = response_buffer.getvalue()
                        if complete_response.strip():
                            await repo.save_message(
                                company_id=company_id,
                                chat_id=chat_id,
                                role="ai",
                                content=complete_response,
                            )
                    except Exception:
                        pass

            async for chunk in generate_response():
                yield chunk

        except Exception as e:
            error_msg = str(e)
            if "LocalProtocolError" not in error_msg and "Can't send data" not in error_msg:
                error_data = {"error": error_msg, "type": "error"}
                yield f"data: {safe_json_dumps(error_data)}\n\n"

    return chat_id, stream_and_save()


async def get_chat_history(
    company_id: str, user_id: str, user_type: str, chat_id: str
) -> Dict[str, Any]:
    messages = repo.fetch_messages(company_id, chat_id)

    chats = await repo.fetch_company_chats(
        company_id=company_id,
        user_id=user_id if user_type == "user" else None,
        session_id=user_id if user_type == "guest" else None,
    )

    chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
    if not chat_exists:
        raise NotFoundError("Chat not found or access denied")

    return {"messages": messages}


async def list_chats(
    company_id: str, user_id: str, user_type: str
) -> Dict[str, Any]:
    chats = await repo.fetch_company_chats(
        company_id=company_id,
        user_id=user_id if user_type == "user" else None,
        session_id=user_id if user_type == "guest" else None,
    )
    return {"chats": chats}


async def update_chat_title(
    company_id: str, user_id: str, user_type: str, chat_id: str, title: str
) -> Dict[str, str]:
    chats = await repo.fetch_company_chats(
        company_id=company_id,
        user_id=user_id if user_type == "user" else None,
        session_id=user_id if user_type == "guest" else None,
    )

    chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
    if not chat_exists:
        raise NotFoundError("Chat not found or access denied")

    await repo.update_chat_title(company_id, chat_id, title)
    return {"message": "Chat title updated successfully"}


async def delete_chat(
    company_id: str, user_id: str, user_type: str, chat_id: str
) -> Dict[str, str]:
    chats = await repo.fetch_company_chats(
        company_id=company_id,
        user_id=user_id if user_type == "user" else None,
        session_id=user_id if user_type == "guest" else None,
    )

    chat_exists = any(chat["chat_id"] == chat_id for chat in chats)
    if not chat_exists:
        raise NotFoundError("Chat not found or access denied")

    await repo.delete_chat(company_id, chat_id)
    return {"message": "Chat deleted successfully"}


async def get_company_info(company_id: str) -> Dict[str, Any]:
    company = await repo.get_company(company_id)
    if not company:
        raise NotFoundError("Company not found")
    return {
        "company": {
            "company_id": company["company_id"],
            "name": company["name"],
            "plan": company["plan"],
            "status": company["status"],
        }
    }
