"""
Custom Pinecone retriever implementation.
Uses shared index with namespace isolation per company.
"""

from typing import List, Any
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field


class DirectPineconeRetriever(BaseRetriever):
    """
    Custom retriever that uses direct Pinecone queries for reliable document retrieval.
    Uses namespace isolation for multi-tenancy.
    """

    pinecone_index: Any = Field(description="Pinecone index object")
    embedding_function: Any = Field(description="Embedding function")
    top_k: int = Field(default=8, description="Number of documents to retrieve")

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Retrieve documents relevant to the query."""
        try:
            # Generate embedding for the query
            query_embedding = self.embedding_function.embed_query(query)

            # Query Pinecone directly using the namespace set in the index
            # Note: namespace is already set when the index object was created
            results = self.pinecone_index.query(
                vector=query_embedding,
                top_k=self.top_k,
                include_metadata=True,
            )

            # Convert results to LangChain documents
            documents = []
            for match in results.matches:
                if hasattr(match, "metadata") and match.metadata:
                    text = match.metadata.get("text", "")
                    if text.strip():  # Only add non-empty documents
                        doc = Document(
                            page_content=text,
                            metadata={
                                **match.metadata,
                                "score": (
                                    match.score if hasattr(match, "score") else 0.0
                                ),
                            },
                        )
                        documents.append(doc)

            return documents

        except Exception:
            return Exception


def create_company_retriever(
    pinecone_index: Any, embedding_function: Any, top_k: int = 8
) -> DirectPineconeRetriever:
    """
    Create a custom retriever for a company.
    Uses shared index with namespace isolation.

    Args:
        pinecone_index: Pinecone index instance (with namespace set)
        embedding_function: Embedding function
        top_k: Number of documents to retrieve

    Returns:
        Direct Pinecone retriever instance
    """
    return DirectPineconeRetriever(
        pinecone_index=pinecone_index,
        embedding_function=embedding_function,
        top_k=top_k,
    )