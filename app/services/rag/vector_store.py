"""
Vector store operations for Pinecone.
Each company gets their own dedicated Pinecone index.
"""

from typing import List, Dict
from langchain_pinecone import PineconeVectorStore
from .pinecone_client import (
    get_pinecone_client,
    get_company_index_name,
    ensure_company_index_exists,
    delete_company_index,
)
from .embeddings import create_embedding_function


# Cache for vector stores
_company_vector_stores: Dict[str, PineconeVectorStore] = {}


def create_company_vector_store(
    company_id: str, doc_chunks: List[str]
) -> PineconeVectorStore:
    """
    Create a company-specific vector store with the provided document chunks.
    Each company gets their own dedicated Pinecone index.

    Args:
        company_id: Company ID
        doc_chunks: List of text chunks to embed

    Returns:
        Company-specific vector store
    """
    global _company_vector_stores

    # Ensure company-specific index exists
    ensure_company_index_exists(company_id)

    # Get company-specific index name
    index_name = get_company_index_name(company_id)

    # Create embeddings
    embedding_function = create_embedding_function()

    # Create vector store with company-specific index
    try:
        vector_store = PineconeVectorStore.from_texts(
            texts=doc_chunks,
            embedding=embedding_function,
            index_name=index_name,
            # No namespace needed - each company has their own index
            text_key="text",
            metadatas=[
                {"source": f"company_{company_id}", "chunk_id": i}
                for i in range(len(doc_chunks))
            ],
        )

    except Exception as vs_error:
        raise vs_error

    # Cache the vector store
    _company_vector_stores[company_id] = vector_store

    return vector_store


def get_company_vector_store(company_id: str) -> PineconeVectorStore:
    """
    Get or create a company-specific vector store.
    Each company gets their own dedicated Pinecone index.

    Args:
        company_id: Company ID

    Returns:
        Company-specific vector store
    """
    global _company_vector_stores

    # Check if we have a cached vector store
    if company_id in _company_vector_stores:
        return _company_vector_stores[company_id]

    # Ensure company-specific index exists
    ensure_company_index_exists(company_id)

    # Get company-specific index name
    index_name = get_company_index_name(company_id)

    # Create embeddings
    embedding_function = create_embedding_function()

    # Create vector store connection with company-specific index
    pinecone_index = get_pinecone_client().Index(index_name)

    vector_store = PineconeVectorStore(
        index=pinecone_index,
        embedding=embedding_function,
        # No namespace needed - each company has their own index
    )

    # Cache the vector store
    _company_vector_stores[company_id] = vector_store

    return vector_store


def clear_company_knowledge_base(company_id: str) -> bool:
    """
    Clear all knowledge base content for a company by deleting all vectors in their index.

    Args:
        company_id: Company ID

    Returns:
        True if successful
    """
    try:
        # Get company-specific index name
        index_name = get_company_index_name(company_id)

        # Delete all vectors in the company's index
        index = get_pinecone_client().Index(index_name)
        index.delete(delete_all=True)

        return True

    except Exception:
        return False


def delete_company_knowledge_base(company_id: str) -> bool:
    """
    Completely delete a company's knowledge base index.
    This removes the entire index, not just the vectors.

    Args:
        company_id: Company ID

    Returns:
        True if successful
    """
    try:
        # Remove from cache
        if company_id in _company_vector_stores:
            del _company_vector_stores[company_id]

        # Delete the entire index
        return delete_company_index(company_id)

    except Exception:
        return False


def get_vector_store_cache() -> Dict[str, PineconeVectorStore]:
    """Get the vector store cache for testing/debugging."""
    return _company_vector_stores


def clear_vector_store_cache():
    """Clear the vector store cache."""
    global _company_vector_stores
    _company_vector_stores.clear()