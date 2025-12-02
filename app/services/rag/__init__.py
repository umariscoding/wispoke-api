"""
RAG (Retrieval-Augmented Generation) service module.

This module provides all functionality for RAG operations including:
- API key management
- Pinecone vector store operations
- Embeddings creation
- Document processing
- RAG chain creation and management
- Response streaming
"""

from .api_keys import (
    check_groq_key,
    get_groq_api_key,
    check_openai_key,
    get_openai_api_key,
    check_pinecone_key,
    get_pinecone_api_key,
)
from .pinecone_client import (
    get_pinecone_client,
    get_company_index_name,  # Legacy - now returns shared index
    get_shared_index_name,
    ensure_company_index_exists,  # Legacy - now ensures shared index
    ensure_shared_index_exists,
    delete_company_knowledge_base_vectors,
)
from .embeddings import create_embedding_function
from .vector_store import (
    get_company_vector_store,
    get_vector_store_cache,
    clear_vector_store_cache,
    clear_company_knowledge_base,
    delete_company_knowledge_base,
)
from .retriever import create_company_retriever
from .llm import create_llm, get_available_models, GROQ_MODEL_MAP
from .rag_chain import (
    get_company_rag_chain,
    get_rag_chain_cache,
    clear_rag_chain_cache,
)
from .streaming import stream_company_response
from .document_processor import process_company_document
from .cache import (
    clear_company_cache,
    clear_all_cache,
    clear_cache,
    force_refresh_all_rag_chains,
)
from .chains import (
    create_conversational_rag_chain,
    create_contextualization_chain,
    create_retrieval_chain,
    create_qa_chain,
    format_chat_history_for_contextualization,
    format_chat_history_for_qa,
)
from .prompts import (
    contextualize_system_prompt,
    contextualize_user_prompt,
    qa_system_prompt,
    qa_user_prompt,
    get_contextualize_prompt_template,
    get_qa_prompt_template,
)

__all__ = [
    # API Keys
    "check_groq_key",
    "get_groq_api_key",
    "check_openai_key",
    "get_openai_api_key",
    "check_pinecone_key",
    "get_pinecone_api_key",
    # Pinecone
    "get_pinecone_client",
    "get_company_index_name",  # Legacy
    "get_shared_index_name",
    "ensure_company_index_exists",  # Legacy
    "ensure_shared_index_exists",
    "delete_company_knowledge_base_vectors",
    # Embeddings
    "create_embedding_function",
    # Vector Store
    "get_company_vector_store",
    "get_vector_store_cache",
    "clear_vector_store_cache",
    "clear_company_knowledge_base",
    "delete_company_knowledge_base",
    # Retriever
    "create_company_retriever",
    # LLM
    "create_llm",
    "get_available_models",
    "GROQ_MODEL_MAP",
    # RAG Chain
    "get_company_rag_chain",
    "get_rag_chain_cache",
    "clear_rag_chain_cache",
    # Streaming
    "stream_company_response",
    # Document Processing
    "process_company_document",
    # Cache Management
    "clear_company_cache",
    "clear_all_cache",
    "clear_cache",
    "force_refresh_all_rag_chains",
    # Chains
    "create_conversational_rag_chain",
    "create_contextualization_chain",
    "create_retrieval_chain",
    "create_qa_chain",
    "format_chat_history_for_contextualization",
    "format_chat_history_for_qa",
    # Prompts
    "contextualize_system_prompt",
    "contextualize_user_prompt",
    "qa_system_prompt",
    "qa_user_prompt",
    "get_contextualize_prompt_template",
    "get_qa_prompt_template",
]