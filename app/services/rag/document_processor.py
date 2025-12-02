"""
Document processing for RAG system.
"""

from typing import Optional
from app.db.operations.document import update_document_embeddings_status
from app.services.document_processing.text_splitter import split_text_for_txt
from .vector_store import get_company_vector_store
from .cache import clear_company_cache


async def process_company_document(
    company_id: str, document_content: str, doc_id: Optional[str] = None
) -> bool:
    """
    Process a document for a company's knowledge base.

    Args:
        company_id: Company ID
        document_content: Document content to process
        doc_id: Document ID for tracking

    Returns:
        True if processing was successful
    """
    try:
        # Split document into chunks
        doc_chunks = split_text_for_txt(document_content)

        # Get or create company vector store
        vector_store = get_company_vector_store(company_id)

        # Add document chunks to vector store with metadata
        metadatas = [
            {
                "source": f"document_{doc_id}" if doc_id else "uploaded_document",
                "chunk_id": i,
                "company_id": company_id,
            }
            for i in range(len(doc_chunks))
        ]

        vector_store.add_texts(texts=doc_chunks, metadatas=metadatas)

        # Clear RAG chain cache for this company to force refresh
        clear_company_cache(company_id)

        # Update document status if doc_id is provided
        if doc_id:
            try:
                await update_document_embeddings_status(doc_id, "completed")
            except Exception:
                pass

        return True

    except Exception:
        # Update document status to failed if doc_id is provided
        if doc_id:
            try:
                await update_document_embeddings_status(doc_id, "failed")
            except Exception:
                pass

        return False