# app/db/supabase_db.py
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import os

from supabase import create_client, Client
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

# Config
from app.core.config import settings
from app.utils.password import get_password_hash, verify_password

# Initialize Supabase client (service_role key recommended for backend)
def check_supabase_key():
    if not settings.supabase_key:
        raise ValueError("SUPABASE  API key is not set in the environment variables.")
    return settings.supabase_key

def check_supabase_url():
    if not settings.supabase_url:
        raise ValueError("SupaBase URL is not set in the environment variables.")
    return settings.supabase_url
db: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Helper
def now_iso() -> str:
    return datetime.now().isoformat()

def generate_id() -> str:
    return str(uuid.uuid4())

# =============================================================================
# COMPANY MANAGEMENT
# =============================================================================

async def create_company(name: str, email: str, password: str) -> Dict[str, Any]:
    slug = name.lower().replace(" ", "-").replace("_", "-")
    while db.table("companies").select("slug").eq("slug", slug).execute().data:
        slug += "-" + str(int(time.time() * 1000))[-4:]

    response = db.table("companies").insert({
        "company_id": generate_id(),
        "name": name,
        "email": email,
        "password_hash": get_password_hash(password),
        "slug": slug,
        "plan": "free",
        "status": "active",
        "is_published": False
    }).execute()

    if not response.data:
        raise ValueError("Company with this email already exists" if "unique" in str(response.error) else "Failed to create company")

    c = response.data[0]
    return {
        "company_id": c["company_id"],
        "name": c["name"],
        "email": c["email"],
        "plan": c["plan"],
        "status": c["status"],
        "slug": c["slug"],
        "is_published": c["is_published"],
        "published_at": c["published_at"],
        "chatbot_title": c["chatbot_title"],
        "chatbot_description": c["chatbot_description"],
        "created_at": c["created_at"]
    }

async def authenticate_company(email: str, password: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("email", email).execute()
    if not res.data:
        return None
    company = res.data[0]
    if verify_password(password, company["password_hash"]):
        return {
            "company_id": company["company_id"],
            "name": company["name"],
            "email": company["email"],
            "plan": company["plan"],
            "status": company["status"],
            "slug": company["slug"],
            "is_published": company["is_published"],
            "published_at": company["published_at"],
            "chatbot_title": company["chatbot_title"],
            "chatbot_description": company["chatbot_description"],
            "created_at": company["created_at"]
        }
    return None

async def get_company_by_id(company_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("company_id", company_id).execute()
    if not res.data:
        return None
    c = res.data[0]
    return {
        "company_id": c["company_id"],
        "name": c["name"],
        "email": c["email"],
        "slug": c["slug"],
        "plan": c["plan"],
        "status": c["status"],
        "is_published": c["is_published"],
        "published_at": c["published_at"],
        "chatbot_title": c["chatbot_title"],
        "chatbot_description": c["chatbot_description"],
        "settings": c.get("settings", {}),
        "created_at": c["created_at"]
    }

async def get_company_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("slug", slug).execute()
    if not res.data:
        return None
    c = res.data[0]
    return {
        "company_id": c["company_id"],
        "name": c["name"],
        "email": c["email"],
        "slug": c["slug"],
        "plan": c["plan"],
        "status": c["status"],
        "is_published": c["is_published"],
        "published_at": c["published_at"],
        "chatbot_title": c["chatbot_title"],
        "chatbot_description": c["chatbot_description"],
        "created_at": c["created_at"]
    }

async def update_company_slug(company_id: str, slug: str) -> bool:
    check = db.table("companies").select("company_id").eq("slug", slug).neq("company_id", company_id).execute()
    if check.data:
        raise ValueError("Slug already exists")
    res = db.table("companies").update({"slug": slug, "updated_at": now_iso()}).eq("company_id", company_id).execute()
    return len(res.data) > 0

async def update_chatbot_info(company_id: str, chatbot_title: Optional[str] = None, chatbot_description: Optional[str] = None) -> bool:
    update_data = {"updated_at": now_iso()}
    if chatbot_title is not None:
        update_data["chatbot_title"] = chatbot_title
    if chatbot_description is not None:
        update_data["chatbot_description"] = chatbot_description
    if len(update_data) == 1:
        return True
    res = db.table("companies").update(update_data).eq("company_id", company_id).execute()
    return bool(res.data)

async def publish_chatbot(company_id: str, is_published: bool) -> bool:
    data = {
        "is_published": is_published,
        "updated_at": now_iso(),
        "published_at": now_iso() if is_published else None
    }
    res = db.table("companies").update(data).eq("company_id", company_id).execute()
    return bool(res.data)

async def get_published_company_info(slug: str) -> Optional[Dict[str, Any]]:
    res = db.table("companies").select("*").eq("slug", slug).eq("is_published", True).eq("status", "active").execute()
    if not res.data:
        return None
    c = res.data[0]
    return {
        "company_id": c["company_id"],
        "name": c["name"],
        "slug": c["slug"],
        "chatbot_title": c["chatbot_title"] or c["name"],
        "chatbot_description": c["chatbot_description"] or f"Chat with {c['name']}",
        "published_at": c["published_at"]
    }

# =============================================================================
# USER & GUEST SESSION MANAGEMENT
# =============================================================================

async def create_user(company_id: str, email: str, password: str, name: str) -> Dict[str, Any]:
    check = db.table("company_users").select("user_id").eq("company_id", company_id).eq("email", email).execute()
    if check.data:
        raise ValueError(f"User with email {email} already exists in this company")

    res = db.table("company_users").insert({
        "user_id": generate_id(),
        "company_id": company_id,
        "email": email,
        "password_hash": get_password_hash(password),
        "name": name
    }).execute()

    u = res.data[0]
    return {
        "user_id": u["user_id"],
        "company_id": u["company_id"],
        "email": u["email"],
        "name": u["name"],
        "is_anonymous": u["is_anonymous"],
        "created_at": u["created_at"]
    }

async def authenticate_user(company_id: str, email: str, password: str) -> Optional[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("company_id", company_id).eq("email", email).execute()
    if not res.data:
        return None
    user = res.data[0]
    if user["password_hash"] and verify_password(password, user["password_hash"]):
        return {
            "user_id": user["user_id"],
            "company_id": user["company_id"],
            "email": user["email"],
            "name": user["name"],
            "is_anonymous": user["is_anonymous"],
            "created_at": user["created_at"]
        }
    return None

async def create_guest_session(company_id: str, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
    expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
    res = db.table("guest_sessions").insert({
        "session_id": generate_id(),
        "company_id": company_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "expires_at": expires_at
    }).execute()
    s = res.data[0]
    return {
        "session_id": s["session_id"],
        "company_id": s["company_id"],
        "ip_address": s["ip_address"],
        "user_agent": s["user_agent"],
        "expires_at": s["expires_at"],
        "created_at": s["created_at"]
    }

async def get_guest_session(session_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("guest_sessions").select("*").eq("session_id", session_id).execute()
    if not res.data:
        return None
    s = res.data[0]
    if datetime.fromisoformat(s["expires_at"].replace("Z", "+00:00")) < datetime.now(datetime.UTC):
        return None
    return {
        "session_id": s["session_id"],
        "company_id": s["company_id"],
        "expires_at": s["expires_at"],
        "created_at": s["created_at"],
        "ip_address": s["ip_address"],
        "user_agent": s["user_agent"]
    }

async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return None
    u = res.data[0]
    return {
        "user_id": u["user_id"],
        "company_id": u["company_id"],
        "email": u["email"],
        "name": u["name"],
        "is_anonymous": u["is_anonymous"],
        "created_at": u["created_at"]
    }

async def get_users_by_company_id(company_id: str) -> List[Dict[str, Any]]:
    res = db.table("company_users").select("*").eq("company_id", company_id).execute()
    if not res.data:
        return []
    return [
        {
            "user_id": u["user_id"],
            "company_id": u["company_id"],
            "email": u["email"],
            "name": u["name"],
            "is_anonymous": u["is_anonymous"],
            "created_at": u["created_at"]
        }
        for u in res.data
    ]

# =============================================================================
# CHAT MANAGEMENT
# =============================================================================

async def save_chat(company_id: str, chat_id: str, title: str, user_id: Optional[str] = None, session_id: Optional[str] = None):
    data = {
        "chat_id": chat_id,
        "company_id": company_id,
        "title": title,
        "user_id": user_id,
        "session_id": session_id,
        "is_guest": session_id is not None
    }
    db.table("chats").upsert(data, on_conflict="chat_id,company_id").execute()

async def save_message(company_id: str, chat_id: str, role: str, content: str):
    # Ensure chat exists
    chat = db.table("chats").select("chat_id").eq("chat_id", chat_id).eq("company_id", company_id).execute()
    if not chat.data:
        await save_chat(company_id, chat_id, "New Chat", session_id="guest")

    db.table("messages").insert({
        "message_id": generate_id(),
        "chat_id": chat_id,
        "company_id": company_id,
        "role": role,
        "content": content,
        "timestamp": int(time.time())
    }).execute()

async def fetch_messages(company_id: str, chat_id: str) -> List[Dict[str, Any]]:
    res = db.table("messages")\
        .select("role, content, timestamp")\
        .eq("chat_id", chat_id)\
        .eq("company_id", company_id)\
        .order("timestamp")\
        .execute()
    return res.data or []

async def fetch_company_chats(company_id: str, user_id: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query = db.table("chats").select("chat_id, title, is_guest, is_deleted, created_at")\
        .eq("company_id", company_id)\
        .eq("is_deleted", False)

    if user_id:
        query = query.eq("user_id", user_id)
    elif session_id:
        query = query.eq("session_id", session_id)

    res = query.execute()
    return res.data or []

async def update_chat_title(company_id: str, chat_id: str, new_title: str):
    db.table("chats").update({"title": new_title}).eq("chat_id", chat_id).eq("company_id", company_id).execute()

async def delete_chat(company_id: str, chat_id: str):
    db.table("chats").update({"is_deleted": True}).eq("chat_id", chat_id).eq("company_id", company_id).execute()

async def delete_all_chats(company_id: str):
    db.table("chats").update({"is_deleted": True}).eq("company_id", company_id).execute()

def load_session_history(company_id: str, chat_id: str) -> ChatMessageHistory:
    history = ChatMessageHistory()
    messages = fetch_messages(company_id, chat_id)
    for msg in messages:
        if msg["role"] == "human":
            history.add_user_message(msg["content"])
        elif msg["role"] == "ai":
            history.add_ai_message(msg["content"])
    return history

# =============================================================================
# KNOWLEDGE BASE & DOCUMENTS
# =============================================================================

async def get_or_create_knowledge_base(company_id: str, name: str = "Default Knowledge Base", description: str = "Company knowledge base") -> Dict[str, Any]:
    res = db.table("knowledge_bases").select("*").eq("company_id", company_id).execute()
    if res.data:
        return res.data[0]
    res = db.table("knowledge_bases").insert({
        "kb_id": generate_id(),
        "company_id": company_id,
        "name": name,
        "description": description,
        "status": "ready",
        "file_count": 0
    }).execute()
    return res.data[0]

async def save_document(
    kb_id: str,
    filename: str,
    content: str,
    content_type: str = "text/plain",
    file_url: str = None
) -> Dict[str, Any]:
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

async def get_company_documents(company_id: str) -> List[Dict[str, Any]]:
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

async def get_document_content(doc_id: str) -> Optional[str]:
    res = db.table("documents").select("content").eq("doc_id", doc_id).execute()
    return res.data[0]["content"] if res.data else None

async def update_document_embeddings_status(doc_id: str, status: str):
    db.table("documents").update({"embeddings_status": status}).eq("doc_id", doc_id).execute()

async def delete_document(doc_id: str, company_id: str) -> bool:
    # First get the document with its kb_id
    doc_res = db.table("documents")\
        .select("kb_id")\
        .eq("doc_id", doc_id)\
        .execute()

    if not doc_res.data:
        return False

    kb_id = doc_res.data[0]["kb_id"]

    # Verify the knowledge base belongs to the company
    kb_check = db.table("knowledge_bases")\
        .select("kb_id")\
        .eq("kb_id", kb_id)\
        .eq("company_id", company_id)\
        .execute()

    if not kb_check.data:
        return False

    # Delete the document
    db.table("documents").delete().eq("doc_id", doc_id).execute()
    db.rpc("decrement_kb_file_count", {"kb_id_param": kb_id}).execute()
    return True

# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

DEFAULT_COMPANY_ID = "default-company"

async def fetch_all_chats() -> List[Dict[str, Any]]:
    return await fetch_company_chats(DEFAULT_COMPANY_ID)

async def save_message_old(chat_id: str, role: str, content: str):
    return await save_message(DEFAULT_COMPANY_ID, chat_id, role, content)

async def save_chat_old(chat_id: str, title: str):
    return await save_chat(DEFAULT_COMPANY_ID, chat_id, title)

async def fetch_messages_old(chat_id: str) -> List[Dict[str, Any]]:
    return await fetch_messages(DEFAULT_COMPANY_ID, chat_id)

async def update_chat_title_old(chat_id: str, new_title: str):
    return await update_chat_title(DEFAULT_COMPANY_ID, chat_id, new_title)

async def delete_chat_old(chat_id: str):
    return await delete_chat(DEFAULT_COMPANY_ID, chat_id)

async def delete_all_chats_old():
    return await delete_all_chats(DEFAULT_COMPANY_ID)

def load_session_history_old(chat_id: str) -> ChatMessageHistory:
    return load_session_history(DEFAULT_COMPANY_ID, chat_id)