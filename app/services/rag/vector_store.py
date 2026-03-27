"""
Vector store operations for Pinecone.
Uses a single shared index with namespace isolation for multi-tenancy.
Includes TTL-based cache eviction.
"""

import time
import logging
from typing import List, Dict, Tuple, Any

from langchain_pinecone import PineconeVectorStore

from .pinecone_client import (
    get_pinecone_client,
    get_shared_index_name,
    ensure_shared_index_exists,
    delete_company_knowledge_base_vectors,
)
from .providers import create_embedding_function

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600  # 1 hour
_company_vector_stores: Dict[str, Tuple[PineconeVectorStore, float]] = {}


def _is_expired(created_at: float) -> bool:
    return (time.time() - created_at) > _CACHE_TTL_SECONDS


def create_company_vector_store(
    company_id: str, doc_chunks: List[str]
) -> PineconeVectorStore:
    global _company_vector_stores

    ensure_shared_index_exists()
    index_name = get_shared_index_name()
    embedding_function = create_embedding_function()

    vector_store = PineconeVectorStore.from_texts(
        texts=doc_chunks,
        embedding=embedding_function,
        index_name=index_name,
        namespace=company_id,
        text_key="text",
        metadatas=[
            {"company_id": company_id, "source": f"company_{company_id}", "chunk_id": i}
            for i in range(len(doc_chunks))
        ],
    )

    _company_vector_stores[company_id] = (vector_store, time.time())
    return vector_store


def get_company_vector_store(company_id: str) -> PineconeVectorStore:
    global _company_vector_stores

    if company_id in _company_vector_stores:
        vs, created_at = _company_vector_stores[company_id]
        if not _is_expired(created_at):
            return vs
        del _company_vector_stores[company_id]

    ensure_shared_index_exists()
    index_name = get_shared_index_name()
    embedding_function = create_embedding_function()
    pinecone_index = get_pinecone_client().Index(index_name)

    vector_store = PineconeVectorStore(
        index=pinecone_index,
        embedding=embedding_function,
        namespace=company_id,
    )

    _company_vector_stores[company_id] = (vector_store, time.time())
    return vector_store


def clear_company_knowledge_base(company_id: str) -> bool:
    try:
        index_name = get_shared_index_name()
        index = get_pinecone_client().Index(index_name)
        index.delete(delete_all=True, namespace=company_id)
        _company_vector_stores.pop(company_id, None)
        return True
    except Exception:
        logger.error("Failed to clear KB for company %s", company_id, exc_info=True)
        return False


def delete_company_knowledge_base(company_id: str) -> bool:
    try:
        _company_vector_stores.pop(company_id, None)
        return delete_company_knowledge_base_vectors(company_id)
    except Exception:
        logger.error("Failed to delete KB for company %s", company_id, exc_info=True)
        return False


def delete_document_vectors(company_id: str, document_id: str) -> bool:
    try:
        index_name = get_shared_index_name()
        index = get_pinecone_client().Index(index_name)
        index.delete(filter={"document_id": {"$eq": document_id}}, namespace=company_id)
        return True
    except Exception:
        logger.error("Failed to delete vectors for doc %s: %s", document_id, exc_info=True)
        return False


def get_vector_store_cache() -> Dict[str, Any]:
    return _company_vector_stores


def clear_vector_store_cache() -> None:
    global _company_vector_stores
    _company_vector_stores.clear()
