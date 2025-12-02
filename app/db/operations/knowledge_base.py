"""
Knowledge base-related database operations.
"""

from typing import Dict, Any, Optional
from .client import db, generate_id


async def create_knowledge_base(company_id: str, name: str = "Default KB") -> Dict[str, Any]:
    """Create a new knowledge base for a company."""
    res = db.table("knowledge_bases").insert({
        "kb_id": generate_id(),
        "company_id": company_id,
        "name": name,
        "file_count": 0
    }).execute()
    return res.data[0]


async def get_knowledge_base_by_company(company_id: str) -> Optional[Dict[str, Any]]:
    """Get knowledge base for a company."""
    res = db.table("knowledge_bases").select("*").eq("company_id", company_id).execute()
    if not res.data:
        return None
    return res.data[0]


async def get_or_create_knowledge_base(company_id: str) -> Dict[str, Any]:
    """Get existing knowledge base or create a new one."""
    kb = await get_knowledge_base_by_company(company_id)
    if kb:
        return kb
    return await create_knowledge_base(company_id)