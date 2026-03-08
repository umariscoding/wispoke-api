"""
Embedding model initialization and management.
"""

from langchain_cohere import CohereEmbeddings
from app.core.config import EMBEDDING_MODEL
from .api_keys import check_cohere_key, get_cohere_api_key


def create_embedding_function() -> CohereEmbeddings:
    """Create Cohere embeddings function."""
    check_cohere_key()
    return CohereEmbeddings(
        model=EMBEDDING_MODEL, cohere_api_key=get_cohere_api_key()
    )