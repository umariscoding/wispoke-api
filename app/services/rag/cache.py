"""
Cache management for RAG system.
"""

from .vector_store import clear_vector_store_cache, get_vector_store_cache
from .rag_chain import clear_rag_chain_cache, get_rag_chain_cache


def clear_company_cache(company_id: str):
    """
    Clear cache for a specific company.

    Args:
        company_id: Company ID
    """
    vector_stores = get_vector_store_cache()
    rag_chains = get_rag_chain_cache()

    if company_id in vector_stores:
        del vector_stores[company_id]

    if company_id in rag_chains:
        del rag_chains[company_id]


def clear_all_cache():
    """Clear all cached data."""
    clear_vector_store_cache()
    clear_rag_chain_cache()


# Legacy compatibility
def clear_cache():
    """Legacy function for clearing cache."""
    clear_all_cache()


def force_refresh_all_rag_chains():
    """Legacy function for refreshing RAG chains."""
    clear_all_cache()