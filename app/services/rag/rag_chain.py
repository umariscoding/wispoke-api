"""
RAG chain creation and management.
"""

from typing import Dict
from langsmith import traceable
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from app.db.operations.chat import load_session_history
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
def get_company_rag_chain(
    company_id: str, llm_model: str = "Groq"
) -> RunnableWithMessageHistory:
    """
    Get or create a company-specific RAG chain with LangSmith tracing.

    Args:
        company_id: Company ID
        llm_model: LLM model to use

    Returns:
        Company-specific RAG chain
    """
    global _company_rag_chains

    # Initialize company cache if not exists
    if company_id not in _company_rag_chains:
        _company_rag_chains[company_id] = {}

    # Check if we have a cached RAG chain for this company and model
    if llm_model in _company_rag_chains[company_id]:
        return _company_rag_chains[company_id][llm_model]

    # Create fresh components
    ensure_company_index_exists(company_id)
    index_name = get_company_index_name(company_id)
    embedding_function = create_embedding_function()
    pinecone_index = get_pinecone_client().Index(index_name)

    # Create retriever (no namespace needed - company has own index)
    retriever = create_company_retriever(pinecone_index, embedding_function)

    # Create LLM
    llm = create_llm(llm_model)

    # Create conversational RAG chain
    try:
        rag_chain = create_conversational_rag_chain(llm, retriever)

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