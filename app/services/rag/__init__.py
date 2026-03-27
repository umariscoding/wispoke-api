"""
RAG (Retrieval-Augmented Generation) service module.

Provides: provider management, Pinecone vector store ops,
document processing, RAG chain management, and response streaming.
"""

from .providers import (
    create_llm,
    create_embedding_function,
    get_available_models,
    get_groq_api_key,
    get_openai_api_key,
    get_anthropic_api_key,
    get_cohere_api_key,
    get_pinecone_api_key,
    GROQ_MODEL_MAP,
)
from .pinecone_client import (
    get_pinecone_client,
    get_company_index_name,
    get_shared_index_name,
    ensure_shared_index_exists,
    delete_company_knowledge_base_vectors,
)
from .vector_store import (
    get_company_vector_store,
    clear_company_knowledge_base,
    delete_company_knowledge_base,
    delete_document_vectors,
)
from .retriever import create_company_retriever
from .chain import (
    get_company_rag_chain,
    clear_rag_chain_cache,
    clear_company_rag_chain_cache,
    clear_company_cache,
    clear_all_cache,
)
from .streaming import stream_company_response
from .document_processor import process_company_document
