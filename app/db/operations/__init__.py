"""
Database operations module.
Exports all database functions from sub-modules.
"""

# Client and utilities
from .client import (
    db,
    generate_id,
    get_supabase_client
)

# Company operations
from .company import (
    create_company,
    get_company_by_api_key,
    get_company_by_id,
    get_company_by_slug,
    get_published_company_info,
    authenticate_company,
    update_company_slug,
    publish_chatbot,
    update_chatbot_info,
)

# User operations
from .user import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_users_by_company_id,
    authenticate_user,
)

# Guest operations
from .guest import (
    create_guest_session,
    get_guest_session
)

# Chat operations
from .chat import (
    create_chat,
    get_chat_by_id,
    get_chats_by_company,
    fetch_company_chats,
    update_chat_title,
    delete_chat,
    load_session_history,
    # Legacy functions
    fetch_all_chats,
    save_chat,
    delete_all_chats,
)

# Message operations
from .message import (
    fetch_messages,
    save_message,
    get_messages_by_chat,
    # Legacy functions
    fetch_messages_old,
    save_message_old,
)

# Knowledge base operations
from .knowledge_base import (
    create_knowledge_base,
    get_knowledge_base_by_company,
    get_or_create_knowledge_base
)

# Document operations
from .document import (
    save_document,
    update_document_embeddings_status,
    get_company_documents,
    delete_document
)

__all__ = [
    # Client
    "db",
    "generate_id",
    "get_supabase_client",
    # Company
    "create_company",
    "get_company_by_api_key",
    "get_company_by_id",
    "get_company_by_slug",
    "get_published_company_info",
    "authenticate_company",
    "update_company_slug",
    "publish_chatbot",
    "update_chatbot_info",
    # User
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_users_by_company_id",
    "authenticate_user",
    # Guest
    "create_guest_session",
    "get_guest_session",
    # Chat
    "create_chat",
    "get_chat_by_id",
    "get_chats_by_company",
    "fetch_company_chats",
    "update_chat_title",
    "delete_chat",
    "load_session_history",
    "fetch_all_chats",  # Legacy
    "save_chat",  # Legacy
    "delete_all_chats",  # Legacy
    # Message
    "fetch_messages",
    "save_message",
    "get_messages_by_chat",
    "fetch_messages_old",  # Legacy
    "save_message_old",  # Legacy
    # Knowledge Base
    "create_knowledge_base",
    "get_knowledge_base_by_company",
    "get_or_create_knowledge_base",
    # Document
    "save_document",
    "update_document_embeddings_status",
    "get_company_documents",
    "delete_document",
]