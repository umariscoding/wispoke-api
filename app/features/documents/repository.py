"""
Document & knowledge-base database operations (synchronous).
"""

from typing import Dict, Any, List, Optional

from app.core.database import db, generate_id
from app.core.pagination import PaginationParams, make_paginated_result


# ---------------------------------------------------------------------------
# Knowledge bases
# ---------------------------------------------------------------------------

def create_knowledge_base(company_id: str, name: str = "Default KB") -> Dict[str, Any]:
    return db.table("knowledge_bases").insert(
        {"kb_id": generate_id(), "company_id": company_id, "name": name, "file_count": 0}
    ).execute().data[0]


def get_knowledge_base_by_company(company_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("knowledge_bases").select("*").eq("company_id", company_id).execute()
    return res.data[0] if res.data else None


def get_or_create_knowledge_base(company_id: str) -> Dict[str, Any]:
    kb = get_knowledge_base_by_company(company_id)
    return kb if kb else create_knowledge_base(company_id)


def fetch_all_knowledge_bases_by_company(company_id: str) -> List[Dict[str, Any]]:
    return db.table("knowledge_bases").select("*").eq("company_id", company_id).execute().data or []


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def _update_kb_file_count(kb_id: str) -> None:
    count_res = db.table("documents").select("doc_id", count="exact").eq("kb_id", kb_id).execute()
    file_count = count_res.count if count_res.count is not None else 0
    db.table("knowledge_bases").update({"file_count": file_count}).eq("kb_id", kb_id).execute()


def save_document(
    kb_id: str, filename: str, content: str,
    content_type: str = "text/plain", file_url: Optional[str] = None,
) -> Dict[str, Any]:
    file_size = len(content.encode("utf-8"))
    doc_data: Dict[str, Any] = {
        "doc_id": generate_id(), "kb_id": kb_id, "filename": filename,
        "content": content, "content_type": content_type,
        "file_size": file_size, "embeddings_status": "pending",
    }

    existing = db.table("documents").select("doc_id").eq("kb_id", kb_id).eq("filename", filename).execute()
    if existing.data:
        doc_data.pop("doc_id")
        res = db.table("documents").update(doc_data).eq("doc_id", existing.data[0]["doc_id"]).execute()
    else:
        res = db.table("documents").insert(doc_data).execute()
        _update_kb_file_count(kb_id)

    result = res.data[0]
    if file_url:
        result["file_url"] = file_url
    return result


def update_document_doc_id(old_doc_id: str, new_doc_id: str) -> None:
    db.table("documents").update({"doc_id": new_doc_id}).eq("doc_id", old_doc_id).execute()


def update_document_embeddings_status(doc_id: str, status: str) -> None:
    db.table("documents").update({"embeddings_status": status}).eq("doc_id", doc_id).execute()


def get_company_documents(company_id: str) -> List[Dict[str, Any]]:
    kb_res = db.table("knowledge_bases").select("kb_id").eq("company_id", company_id).execute()
    if not kb_res.data:
        return []
    kb_id = kb_res.data[0]["kb_id"]
    return db.table("documents").select(
        "doc_id, kb_id, filename, content_type, file_size, embeddings_status, created_at"
    ).eq("kb_id", kb_id).execute().data or []


def get_company_documents_paginated(company_id: str, page: int = 1, page_size: int = 20) -> dict:
    kb_res = db.table("knowledge_bases").select("kb_id").eq("company_id", company_id).execute()
    if not kb_res.data:
        return make_paginated_result([], 0, page, page_size)

    kb_id = kb_res.data[0]["kb_id"]
    p = PaginationParams(page, page_size)
    total = db.table("documents").select("doc_id", count="exact").eq("kb_id", kb_id).execute().count or 0
    data = (
        db.table("documents")
        .select("doc_id, kb_id, filename, content_type, file_size, embeddings_status, created_at")
        .eq("kb_id", kb_id).order("created_at", desc=True)
        .range(p.range_start, p.range_end).execute()
    ).data or []
    return make_paginated_result(data, total, page, page_size)


def delete_document(doc_id: str, company_id: str) -> bool:
    doc_res = db.table("documents").select("kb_id").eq("doc_id", doc_id).execute()
    if not doc_res.data:
        return False
    kb_id = doc_res.data[0]["kb_id"]
    kb_check = db.table("knowledge_bases").select("kb_id").eq("kb_id", kb_id).eq("company_id", company_id).execute()
    if not kb_check.data:
        return False
    db.table("documents").delete().eq("doc_id", doc_id).execute()
    _update_kb_file_count(kb_id)
    return True
