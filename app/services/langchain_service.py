"""
LangChain service module - Re-exports all RAG operations for backward compatibility.

This module has been refactored into smaller, focused modules under app.services.rag/.
All functions are re-exported here to maintain backward compatibility with existing code.

New structure:
- app.services.rag.api_keys - API key validation
- app.services.rag.pinecone_client - Pinecone initialization
- app.services.rag.embeddings - Embedding functions
- app.services.rag.vector_store - Vector store operations
- app.services.rag.retriever - Document retrieval
- app.services.rag.llm - LLM creation
- app.services.rag.rag_chain - RAG chain creation
- app.services.rag.streaming - Response streaming
- app.services.rag.document_processor - Document processing
- app.services.rag.cache - Cache management
- app.services.rag.chains - Manual chain implementations
- app.services.rag.prompts - Prompt templates
"""

from app.services.rag import *

# Legacy compatibility - some functions may have different names
# Ensure all legacy function names are available for backward compatibility
from app.services.rag import (
    get_company_vector_store as get_pinecone_vectorstore,
    stream_company_response as stream_response,
    get_company_rag_chain as get_rag_chain,
)

# Additional legacy functions that may be used elsewhere
def create_embeddings_and_store_text(doc_chunks, company_id="default"):
    """
    Legacy function for creating vector store.

    Args:
        doc_chunks: Document chunks to store
        company_id: Company ID (default: "default")

    Returns:
        Vector store instance
    """
    from app.services.rag import get_company_vector_store

    vector_store = get_company_vector_store(company_id)
    vector_store.add_texts(texts=doc_chunks)
    return vector_store


def setup_company_knowledge_base(company_id, doc_chunks):
    """
    Legacy function for setting up knowledge base.

    Args:
        company_id: Company ID
        doc_chunks: Document chunks to store

    Returns:
        Vector store instance
    """
    from app.services.rag import get_company_vector_store

    vector_store = get_company_vector_store(company_id)
    vector_store.add_texts(texts=doc_chunks)
    return vector_store


def clear_company_knowledge_base(company_id):
    """
    Clear all knowledge base content for a company.
    Each company has their own dedicated Pinecone index.

    Args:
        company_id: Company ID

    Returns:
        bool: True if successful
    """
    from app.services.rag import clear_company_knowledge_base as _clear_kb

    return _clear_kb(company_id)


def initialize_default_knowledge_base(doc_chunks):
    """
    Initialize the default knowledge base for backward compatibility.

    Args:
        doc_chunks: Document chunks to store
    """
    return setup_company_knowledge_base("default", doc_chunks)


def query_pinecone(db, llm_model="Groq", chat_id="abc123", company_id="default"):
    """
    Legacy function for querying pinecone.

    Args:
        db: Vector store (unused in new implementation)
        llm_model: LLM model to use
        chat_id: Chat session ID
        company_id: Company ID

    Returns:
        RAG chain instance
    """
    from app.services.rag import get_company_rag_chain

    return get_company_rag_chain(company_id, llm_model)