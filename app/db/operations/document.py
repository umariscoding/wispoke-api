"""
Document-related database operations.
"""

from typing import Dict, Any, List, Optional
from .client import db, generate_id


async def save_document(
    kb_id: str,
    filename: str,
    content: str,
    content_type: str = "text/plain",
    file_url: str = None
) -> Dict[str, Any]:
    """Save a document to the database."""
    file_size = len(content.encode("utf-8"))
    doc_data = {
        "doc_id": generate_id(),
        "kb_id": kb_id,
        "filename": filename,
        "content": content,
        "content_type": content_type,
        "file_size": file_size,
        "embeddings_status": "pending"
    }

    # Don't add file_url to database for now (column doesn't exist yet)
    # It will be stored in Supabase Storage separately
    # Uncomment the lines below after adding file_url column to documents table
    # if file_url:
    #     doc_data["file_url"] = file_url

    res = db.table("documents").upsert(
        doc_data,
        on_conflict="kb_id,filename"
    ).execute()

    if "created" in res.data[0] or "updated" in res.data[0]:
        db.rpc("increment_kb_file_count", {"kb_id_param": kb_id}).execute()

    # Add file_url to response even if not stored in database
    result = res.data[0]
    if file_url:
        result["file_url"] = file_url

    return result


async def update_document_embeddings_status(doc_id: str, status: str):
    """Update document embeddings status."""
    db.table("documents").update({"embeddings_status": status}).eq("doc_id", doc_id).execute()


async def get_company_documents(company_id: str) -> List[Dict[str, Any]]:
    """Get all documents for a company."""
    # First get the knowledge base for this company
    kb_res = db.table("knowledge_bases")\
        .select("kb_id")\
        .eq("company_id", company_id)\
        .execute()

    if not kb_res.data:
        return []

    kb_id = kb_res.data[0]["kb_id"]

    # Then get documents for this knowledge base
    res = db.table("documents")\
        .select("doc_id, kb_id, filename, content_type, file_size, embeddings_status, created_at")\
        .eq("kb_id", kb_id)\
        .execute()
    return res.data or []


async def delete_document(doc_id: str, company_id: str) -> bool:
    """Delete a document and its associated vectors."""
    import logging

    # Import here to avoid circular imports
    from app.services.rag import delete_document_vectors
    from app.services.rag.cache import clear_company_cache

    logger = logging.getLogger(__name__)

    # First get the document with its kb_id
    doc_res = db.table("documents")\
        .select("kb_id")\
        .eq("doc_id", doc_id)\
        .execute()

    if not doc_res.data:
        logger.warning(f"Document not found: {doc_id}")
        return False

    kb_id = doc_res.data[0]["kb_id"]

    # Verify the knowledge base belongs to the company
    kb_check = db.table("knowledge_bases")\
        .select("kb_id")\
        .eq("kb_id", kb_id)\
        .eq("company_id", company_id)\
        .execute()

    if not kb_check.data:
        logger.warning(f"Knowledge base {kb_id} does not belong to company {company_id}")
        return False

    # Delete vectors from Pinecone first
    try:
        logger.info(f"Deleting vectors for document {doc_id} in company {company_id}")
        success = delete_document_vectors(company_id, doc_id)
        if success:
            logger.info(f"Successfully deleted vectors for document {doc_id}")
        else:
            logger.warning(f"Failed to delete vectors for document {doc_id}")
    except Exception as e:
        # Continue even if vector deletion fails
        logger.error(f"Error deleting vectors for document {doc_id}: {str(e)}")

    # Clear company cache to refresh RAG chain
    try:
        logger.info(f"Clearing cache for company {company_id}")
        clear_company_cache(company_id)
        logger.info(f"Successfully cleared cache for company {company_id}")
    except Exception as e:
        # Continue even if cache clear fails
        logger.error(f"Error clearing cache for company {company_id}: {str(e)}")

    # Delete the document from database
    logger.info(f"Deleting document {doc_id} from database")
    db.table("documents").delete().eq("doc_id", doc_id).execute()
    db.rpc("decrement_kb_file_count", {"kb_id_param": kb_id}).execute()
    logger.info(f"Successfully deleted document {doc_id} from database")

    return True