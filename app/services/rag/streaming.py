"""
Response streaming for RAG chains.
"""

import asyncio
import logging
from typing import AsyncGenerator

from .chain import get_company_rag_chain
from .providers import get_groq_api_key, get_openai_api_key, get_pinecone_api_key, GROQ_MODELS
from app.features.auth.repository import get_company_by_id

logger = logging.getLogger(__name__)


async def stream_company_response(
    company_id: str, query: str, chat_id: str, llm_model: str = "Llama-large"
) -> AsyncGenerator[str, None]:
    """
    Stream response from company-specific RAG chain.
    The llm_model parameter is ignored — model is resolved from DB settings.
    """
    try:
        company = get_company_by_id(company_id)
        resolved_model = (company.get("default_model") or "Llama-large") if company else "Llama-large"

        error = _check_api_key(resolved_model)
        if error:
            yield error
            return

        pinecone_key = get_pinecone_api_key()
        if not pinecone_key or pinecone_key.startswith("your-"):
            yield "Error: Pinecone API key not configured."
            return

        try:
            rag_chain = get_company_rag_chain(company_id, resolved_model)
        except Exception as chain_error:
            error_msg = str(chain_error).lower()
            if "pinecone" in error_msg:
                yield "Error: Knowledge base connection failed. Please ensure documents are uploaded."
            elif any(k in error_msg for k in ("groq", "openai", "api")):
                yield "Error: AI service connection failed. Please check API configuration."
            else:
                yield f"Error: Failed to initialize chat system. Details: {chain_error}"
            return

        try:
            resp = rag_chain.stream(
                {"input": query},
                config={"configurable": {"session_id": chat_id}},
            )
            response_started = False
            for chunk in resp:
                if isinstance(chunk, str) and chunk:
                    response_started = True
                    yield chunk
                    await asyncio.sleep(0.03)
                elif isinstance(chunk, dict) and "answer" in chunk and chunk["answer"]:
                    response_started = True
                    yield chunk["answer"]
                    await asyncio.sleep(0.03)

            if not response_started:
                yield "I apologize, but I couldn't generate a response. Please try again."

        except Exception as stream_error:
            yield f"Error: Failed to generate response. Details: {stream_error}"

    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "unauthorized" in error_msg:
            yield "Error: Invalid or missing API key. Please check your configuration."
        elif "pinecone" in error_msg:
            yield "Error: Pinecone connection failed."
        else:
            yield f"Error: {e}"


def _check_api_key(model: str) -> str | None:
    if model in GROQ_MODELS:
        key = get_groq_api_key()
        if not key or key.startswith("your-"):
            return "Error: Groq API key not configured."
    elif model in ("GPT-4o-mini", "GPT-4o", "GPT-4.1", "GPT-4.1-mini"):
        key = get_openai_api_key()
        if not key or key.startswith("your-"):
            return "Error: OpenAI API key not configured."
    return None
