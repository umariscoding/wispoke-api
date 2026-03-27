"""
Pinecone client initialization and management.

Uses a single shared index with namespace isolation for multi-tenancy.
Each company gets their own namespace for complete data isolation.
"""

import time
import logging

from pinecone import Pinecone, ServerlessSpec
from .providers import get_pinecone_api_key


def _check_pinecone_key():
    if not get_pinecone_api_key():
        raise ValueError("Pinecone API key is not set in environment variables.")

logger = logging.getLogger(__name__)

_pinecone_client = None
SHARED_INDEX_NAME = "chatelio-shared"


def get_pinecone_client() -> Pinecone:
    """Get or create the Pinecone client singleton."""
    global _pinecone_client
    if _pinecone_client is None:
        _check_pinecone_key()
        _pinecone_client = Pinecone(api_key=get_pinecone_api_key())
    return _pinecone_client


def get_shared_index_name() -> str:
    """Return the shared index name used by all companies."""
    return SHARED_INDEX_NAME


def ensure_shared_index_exists() -> None:
    """
    Create the shared Pinecone index if it doesn't exist yet.
    Blocks until the index is ready (up to 5 minutes).
    """
    existing = [idx["name"] for idx in get_pinecone_client().list_indexes()]
    if SHARED_INDEX_NAME in existing:
        return

    get_pinecone_client().create_index(
        name=SHARED_INDEX_NAME,
        dimension=1024,  # Cohere embed-english-v3.0
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

    max_wait, waited = 300, 0
    while not get_pinecone_client().describe_index(SHARED_INDEX_NAME).status["ready"]:
        if waited >= max_wait:
            raise TimeoutError(f"Index creation timed out after {max_wait}s")
        time.sleep(5)
        waited += 5


def delete_company_knowledge_base_vectors(company_id: str) -> bool:
    """Delete all vectors in a company's namespace from the shared index."""
    try:
        index = get_pinecone_client().Index(SHARED_INDEX_NAME)
        index.delete(delete_all=True, namespace=company_id)
        return True
    except Exception:
        logger.error("Failed to delete vectors for company %s", company_id, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Aliases used by rag_chain.py — keep the interface stable
# ---------------------------------------------------------------------------

def get_company_index_name(_company_id: str) -> str:
    """Return the shared index name (company_id is ignored)."""
    return SHARED_INDEX_NAME


def ensure_company_index_exists(_company_id: str) -> None:
    """Ensure the shared index exists (company_id is ignored)."""
    ensure_shared_index_exists()
