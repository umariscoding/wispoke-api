"""
RAG chain creation and management.
"""

from typing import Dict
from langsmith import traceable
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from app.db.operations.chat import load_session_history
from app.db.operations.company import get_company_by_id
from .chains import create_conversational_rag_chain
from .pinecone_client import (
    get_pinecone_client,
    get_company_index_name,
    ensure_company_index_exists,
)
from .embeddings import create_embedding_function
from .retriever import create_company_retriever
from .llm import create_llm


# Cache for RAG chains
_company_rag_chains: Dict[str, Dict[str, RunnableWithMessageHistory]] = {}


@traceable(name="get_company_rag_chain")
async def get_company_rag_chain(
    company_id: str, llm_model: str = "Llama-instant"
) -> RunnableWithMessageHistory:
    """
    Get or create a company-specific RAG chain with LangSmith tracing.
    Uses shared index with namespace isolation per company.

    Args:
        company_id: Company ID (used as namespace)
        llm_model: LLM model to use (default: Llama-instant)

    Returns:
        Company-specific RAG chain with namespace isolation
    """
    global _company_rag_chains

    # Initialize company cache if not exists
    if company_id not in _company_rag_chains:
        _company_rag_chains[company_id] = {}

    # Check if we have a cached RAG chain for this company and model
    if llm_model in _company_rag_chains[company_id]:
        return _company_rag_chains[company_id][llm_model]

    # Fetch company information
    company = await get_company_by_id(company_id)

    # Prepare company context for the prompt
    company_context = {
        "company_name": company.get("name", "our company") if company else "our company",
        "company_email": company.get("email", "support@company.com") if company else "support@company.com",
        "company_description": ""
    }

    # Add chatbot description if available
    if company and company.get("chatbot_description"):
        company_context["company_description"] = f"- Description: {company['chatbot_description']}"

    # Create fresh components
    ensure_company_index_exists(company_id)
    index_name = get_company_index_name(company_id)  # Returns shared index name
    embedding_function = create_embedding_function()
    pinecone_index = get_pinecone_client().Index(index_name)

    # Create retriever with company namespace for isolation
    # Each company has their own namespace in the shared index
    retriever = create_company_retriever(
        pinecone_index,
        embedding_function,
        namespace=company_id  # Use company_id as namespace
    )

    # Create LLM
    llm = create_llm(llm_model)

    # Create conversational RAG chain with company context
    try:
        rag_chain = create_conversational_rag_chain(llm, retriever, company_context)

        # Create session history function
        def get_session_history(chat_id: str) -> BaseChatMessageHistory:
            try:
                return load_session_history(company_id, chat_id)
            except Exception:
                from langchain_core.chat_history import InMemoryChatMessageHistory

                return InMemoryChatMessageHistory()

        # Wrap with message history
        conversational_rag_chain = RunnableWithMessageHistory(
            rag_chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

    except Exception as chain_error:
        raise chain_error

    # Cache the chain
    _company_rag_chains[company_id][llm_model] = conversational_rag_chain

    return conversational_rag_chain


def get_rag_chain_cache() -> Dict[str, Dict[str, RunnableWithMessageHistory]]:
    """Get the RAG chain cache for testing/debugging."""
    return _company_rag_chains


def clear_rag_chain_cache():
    """Clear the RAG chain cache."""
    global _company_rag_chains
    _company_rag_chains.clear()