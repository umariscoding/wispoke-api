"""
Analytics repository — data access for analytics queries.
"""

from typing import Dict, Any, List
from app.db.operations.client import db


async def fetch_all_messages(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("messages").select("*").eq("company_id", company_id).execute()
    return res.data or []


async def fetch_all_users(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("company_id", company_id).execute()
    return res.data or []


async def fetch_all_chats(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("chats").select("*").eq("company_id", company_id).eq("is_deleted", False).execute()
    return res.data or []


async def fetch_all_knowledge_bases(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("knowledge_bases").select("*").eq("company_id", company_id).execute()
    return res.data or []


async def fetch_all_guest_sessions(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("guest_sessions").select("*").eq("company_id", company_id).execute()
    return res.data or []
