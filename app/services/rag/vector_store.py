"""
Vector store operations for Pinecone.
Uses a single shared index with namespace isolation for multi-tenancy.
Each company gets their own namespace for complete data isolation.
"""

from typing import List, Dict
from langchain_pinecone import PineconeVectorStore
from .pinecone_client import (
    get_pinecone_client,
    get_shared_index_name,
    ensure_shared_index_exists,
    delete_company_knowledge_base_vectors,
)
from .embeddings import create_embedding_function


# Cache for vector stores - now keyed by company_id but all use shared index
_company_vector_stores: Dict[str, PineconeVectorStore] = {}


def create_company_vector_store(
    company_id: str, doc_chunks: List[str]
) -> PineconeVectorStore:
    """
    Create a company-specific vector store with the provided document chunks.
    Uses shared index with namespace isolation per company.

    Args:
        company_id: Company ID
        doc_chunks: List of text chunks to embed

    Returns:
        Company-specific vector store
    """
    global _company_vector_stores

    # Ensure shared index exists
    ensure_shared_index_exists()

    # Get shared index name
    index_name = get_shared_index_name()

    # Create embeddings
    embedding_function = create_embedding_function()

    # Create vector store with shared index and namespace for company isolation
    try:
        vector_store = PineconeVectorStore.from_texts(
            texts=doc_chunks,
            embedding=embedding_function,
            index_name=index_name,
            namespace=company_id,  # Use namespace for complete isolation
            text_key="text",
            metadatas=[
                {
                    "company_id": company_id,  # Also add to metadata for extra safety
                    "source": f"company_{company_id}",
                    "chunk_id": i,
                }
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
    Uses shared index with company_id metadata filtering.

    Args:
        company_id: Company ID

    Returns:
        Company-specific vector store with filtering
    """
    global _company_vector_stores

    # Check if we have a cached vector store
    if company_id in _company_vector_stores:
        return _company_vector_stores[company_id]

    # Ensure shared index exists
    ensure_shared_index_exists()

    # Get shared index name
    index_name = get_shared_index_name()

    # Create embeddings
    embedding_function = create_embedding_function()

    # Create vector store connection with shared index
    pinecone_index = get_pinecone_client().Index(index_name)

    # Create vector store with namespace for company isolation
    # Note: We'll use company_id as namespace for better isolation
    vector_store = PineconeVectorStore(
        index=pinecone_index,
        embedding=embedding_function,
        namespace=company_id,  # Use company_id as namespace for isolation
    )

    # Cache the vector store
    _company_vector_stores[company_id] = vector_store

    return vector_store


def clear_company_knowledge_base(company_id: str) -> bool:
    """
    Clear all knowledge base content for a company by deleting their namespace.

    Args:
        company_id: Company ID

    Returns:
        True if successful
    """
    try:
        # Get shared index
        index_name = get_shared_index_name()
        index = get_pinecone_client().Index(index_name)

        # Delete all vectors in the company's namespace
        index.delete(delete_all=True, namespace=company_id)

        # Clear cache for this company
        if company_id in _company_vector_stores:
            del _company_vector_stores[company_id]

        return True

    except Exception:
        return False


def delete_company_knowledge_base(company_id: str) -> bool:
    """
    Delete a company's knowledge base by removing their namespace.
    This removes all vectors for the company from the shared index.

    Args:
        company_id: Company ID

    Returns:
        True if successful
    """
    try:
        # Remove from cache
        if company_id in _company_vector_stores:
            del _company_vector_stores[company_id]

        # Delete all vectors for this company using their namespace
        return delete_company_knowledge_base_vectors(company_id)

    except Exception:
        return False


def delete_document_vectors(company_id: str, document_id: str) -> bool:
    """
    Delete all vectors associated with a specific document.
    Uses metadata filtering to delete only vectors with the given document_id.

    Args:
        company_id: Company ID (namespace)
        document_id: Document ID to delete vectors for

    Returns:
        True if successful
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Get shared index
        index_name = get_shared_index_name()
        logger.info(f"Getting Pinecone index: {index_name}")
        index = get_pinecone_client().Index(index_name)

        # Delete vectors with matching document_id in the company's namespace
        # Pinecone's delete with filter deletes all vectors matching the metadata filter
        logger.info(f"Deleting vectors from Pinecone - namespace: {company_id}, document_id: {document_id}")
        index.delete(
            filter={"document_id": {"$eq": document_id}},
            namespace=company_id
        )
        logger.info(f"Pinecone delete operation completed for document {document_id}")

        return True

    except Exception as e:
        logger.error(f"Failed to delete vectors from Pinecone for document {document_id}: {str(e)}")
        return False


def get_vector_store_cache() -> Dict[str, PineconeVectorStore]:
    """Get the vector store cache for testing/debugging."""
    return _company_vector_stores


def clear_vector_store_cache():
    """Clear the vector store cache."""
    global _company_vector_stores
    _company_vector_stores.clear()