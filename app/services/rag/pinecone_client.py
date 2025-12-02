"""
Pinecone client initialization and management.
"""

import time
from pinecone import Pinecone, ServerlessSpec
from .api_keys import check_pinecone_key, get_pinecone_api_key


# Initialize Pinecone (lazy initialization)
_pinecone_client = None


def get_pinecone_client() -> Pinecone:
    """Get or create Pinecone client instance."""
    global _pinecone_client
    if _pinecone_client is None:
        check_pinecone_key()
        _pinecone_client = Pinecone(api_key=get_pinecone_api_key())
    return _pinecone_client


def get_company_index_name(company_id: str) -> str:
    """
    Generate a company-specific index name.

    Args:
        company_id: Company ID

    Returns:
        Company-specific index name
    """
    # Sanitize company_id to ensure valid index name
    # Pinecone index names must be lowercase alphanumeric with hyphens
    sanitized_id = company_id.lower().replace("_", "-")
    return f"chatelio-{sanitized_id}"


def ensure_company_index_exists(company_id: str):
    """
    Ensure a company-specific index exists with optimal configuration.

    Args:
        company_id: Company ID

    Raises:
        TimeoutError: If index creation times out
        Exception: If index creation fails
    """
    try:
        index_name = get_company_index_name(company_id)

        # Get list of existing indexes
        existing_indexes = [
            index_info["name"]
            for index_info in get_pinecone_client().list_indexes()
        ]

        # Create index if it doesn't exist
        if index_name not in existing_indexes:
            get_pinecone_client().create_index(
                name=index_name,
                dimension=1024,  # Cohere embed-english-v3.0 dimension
                metric="cosine",  # Best for text similarity
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

            # Wait for index to be ready with timeout
            max_wait = 300  # 5 minutes timeout
            waited = 0
            while not get_pinecone_client().describe_index(index_name).status["ready"]:
                if waited >= max_wait:
                    raise TimeoutError(
                        f"Index creation timed out after {max_wait} seconds"
                    )
                time.sleep(5)
                waited += 5

    except Exception as e:
        raise e


def delete_company_index(company_id: str) -> bool:
    """
    Delete a company-specific index.

    Args:
        company_id: Company ID

    Returns:
        True if deletion was successful
    """
    try:
        index_name = get_company_index_name(company_id)
        get_pinecone_client().delete_index(index_name)
        return True
    except Exception:
        return False