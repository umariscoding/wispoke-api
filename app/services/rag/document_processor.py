"""
Document processing for RAG system.
"""

import logging
from typing import Optional

from app.features.documents.repository import update_document_embeddings_status
from app.services.document_processing.text_splitter import split_text_for_txt
from .vector_store import get_company_vector_store
from .chain import clear_company_cache

logger = logging.getLogger(__name__)


async def process_company_document(
    company_id: str, document_content: str, doc_id: Optional[str] = None,
    upload_source: str = "text",
) -> bool:
    """
    Process a document for a company's knowledge base.
    Kept async for compatibility with router-level await, but internal ops are sync.

    upload_source: "text" (free-tier paste) or "file" (Pro-tier PDF/DOCX upload).
    Used at retrieval time to filter out Pro-only documents for free users.
    """
    try:
        doc_chunks = split_text_for_txt(document_content)
        vector_store = get_company_vector_store(company_id)

        metadatas = [
            {
                "source": f"document_{doc_id}" if doc_id else "uploaded_document",
                "chunk_id": i,
                "company_id": company_id,
                "document_id": doc_id or "unknown",
                "upload_source": upload_source,
            }
            for i in range(len(doc_chunks))
        ]

        vector_store.add_texts(texts=doc_chunks, metadatas=metadatas)
        clear_company_cache(company_id)

        if doc_id:
            try:
                update_document_embeddings_status(doc_id, "completed")
            except Exception:
                logger.warning("Failed to update embeddings status for doc %s", doc_id)

        return True

    except Exception:
        logger.error("Failed to process document %s for company %s", doc_id, company_id, exc_info=True)
        if doc_id:
            try:
                update_document_embeddings_status(doc_id, "failed")
            except Exception:
                pass
        return False
