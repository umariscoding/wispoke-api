"""
Documents repository — data access for documents and knowledge bases.
"""

from typing import Dict, Any, List, Optional
from app.db.operations.document import (
    save_document as db_save_document,
    get_company_documents as db_get_company_documents,
    delete_document as db_delete_document,
)
from app.db.operations.knowledge_base import (
    get_or_create_knowledge_base as db_get_or_create_knowledge_base,
)
from app.db.operations.client import generate_id, db


async def get_or_create_knowledge_base(company_id: str) -> Dict[str, Any]:
    return await db_get_or_create_knowledge_base(company_id)


async def save_document(
    kb_id: str, filename: str, content: str,
    content_type: str = "text/plain", file_url: str = None
) -> Dict[str, Any]:
    return await db_save_document(
        kb_id=kb_id, filename=filename, content=content,
        content_type=content_type, file_url=file_url,
    )


async def get_company_documents(company_id: str) -> List[Dict[str, Any]]:
    return await db_get_company_documents(company_id)


async def delete_document(doc_id: str, company_id: str) -> bool:
    return await db_delete_document(doc_id, company_id)


def new_id() -> str:
    return generate_id()


def update_document_doc_id(old_doc_id: str, new_doc_id: str):
    db.table("documents").update({"doc_id": new_doc_id}).eq("doc_id", old_doc_id).execute()
