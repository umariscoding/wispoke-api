"""
Pinecone client initialization and management.

Uses a single shared index with namespace isolation for multi-tenancy.
Each company gets their own namespace for complete data isolation.
"""

import time
from pinecone import Pinecone, ServerlessSpec
from .api_keys import check_pinecone_key, get_pinecone_api_key


# Initialize Pinecone (lazy initialization)
_pinecone_client = None

# Shared index name for all companies
SHARED_INDEX_NAME = "chatelio-shared"


def get_pinecone_client() -> Pinecone:
    """Get or create Pinecone client instance."""
    global _pinecone_client
    if _pinecone_client is None:
        check_pinecone_key()
        _pinecone_client = Pinecone(api_key=get_pinecone_api_key())
    return _pinecone_client


def get_shared_index_name() -> str:
    """
    Get the shared index name used by all companies.

    Returns:
        Shared index name
    """
    return SHARED_INDEX_NAME


def ensure_shared_index_exists():
    """
    Ensure the shared index exists with optimal configuration.
    All companies use this single index with metadata filtering.

    Raises:
        TimeoutError: If index creation times out
        Exception: If index creation fails
    """
    try:
        # Get list of existing indexes
        existing_indexes = [
            index_info["name"]
            for index_info in get_pinecone_client().list_indexes()
        ]

        # Create index if it doesn't exist
        if SHARED_INDEX_NAME not in existing_indexes:
            get_pinecone_client().create_index(
                name=SHARED_INDEX_NAME,
                dimension=1024,  # Cohere embed-english-v3.0 dimension
                metric="cosine",  # Best for text similarity
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

            # Wait for index to be ready with timeout
            max_wait = 300  # 5 minutes timeout
            waited = 0
            while not get_pinecone_client().describe_index(SHARED_INDEX_NAME).status["ready"]:
                if waited >= max_wait:
                    raise TimeoutError(
                        f"Index creation timed out after {max_wait} seconds"
                    )
                time.sleep(5)
                waited += 5

    except Exception as e:
        raise e


# Legacy function for backward compatibility
def get_company_index_name(company_id: str) -> str:
    """
    Legacy function - now returns shared index name.
    Kept for backward compatibility.

    Args:
        company_id: Company ID (ignored)

    Returns:
        Shared index name
    """
    return SHARED_INDEX_NAME


# Legacy function for backward compatibility
def ensure_company_index_exists(company_id: str):
    """
    Legacy function - now ensures shared index exists.
    Kept for backward compatibility.

    Args:
        company_id: Company ID (ignored)
    """
    ensure_shared_index_exists()


def delete_company_knowledge_base_vectors(company_id: str) -> bool:
    """
    Delete all vectors for a specific company from the shared index.
    Uses namespace isolation for complete data separation.

    Args:
        company_id: Company ID

    Returns:
        True if deletion was successful
    """
    try:
        index = get_pinecone_client().Index(SHARED_INDEX_NAME)
        # Delete all vectors in this company's namespace
        index.delete(delete_all=True, namespace=company_id)
        return True
    except Exception:
        return False