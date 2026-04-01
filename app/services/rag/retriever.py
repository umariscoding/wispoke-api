"""
Custom Pinecone retriever implementation.
Uses shared index with namespace isolation per company.
"""

import logging
from typing import List, Any

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field

logger = logging.getLogger(__name__)


class DirectPineconeRetriever(BaseRetriever):
    """
    Custom retriever that queries Pinecone directly with namespace isolation.
    """

    pinecone_index: Any = Field(description="Pinecone index object")
    embedding_function: Any = Field(description="Embedding function")
    namespace: str = Field(description="Namespace for company isolation (company_id)")
    top_k: int = Field(default=8, description="Number of documents to retrieve")
    metadata_filter: dict = Field(default_factory=dict, description="Optional Pinecone metadata filter")

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        try:
            query_embedding = self.embedding_function.embed_query(query)

            query_kwargs: dict = {
                "vector": query_embedding,
                "top_k": self.top_k,
                "include_metadata": True,
                "namespace": self.namespace,
            }
            if self.metadata_filter:
                query_kwargs["filter"] = self.metadata_filter

            results = self.pinecone_index.query(**query_kwargs)

            documents = []
            for match in results.matches:
                if hasattr(match, "metadata") and match.metadata:
                    text = match.metadata.get("text", "")
                    if text.strip():
                        doc = Document(
                            page_content=text,
                            metadata={
                                **match.metadata,
                                "score": match.score if hasattr(match, "score") else 0.0,
                            },
                        )
                        documents.append(doc)

            return documents

        except Exception as e:
            logger.error("Pinecone retrieval failed for namespace %s: %s", self.namespace, e)
            return []


def create_company_retriever(
    pinecone_index: Any,
    embedding_function: Any,
    namespace: str,
    top_k: int = 8,
    metadata_filter: dict | None = None,
) -> DirectPineconeRetriever:
    return DirectPineconeRetriever(
        pinecone_index=pinecone_index,
        embedding_function=embedding_function,
        namespace=namespace,
        top_k=top_k,
        metadata_filter=metadata_filter or {},
    )
