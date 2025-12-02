"""
Database module - Re-exports all operations for backward compatibility.

This file maintains backward compatibility by re-exporting all functions
from the modular operations structure.

New code should import directly from:
- app.db.operations.company
- app.db.operations.user
- app.db.operations.chat
- app.db.operations.message
- app.db.operations.knowledge_base
- app.db.operations.document
- app.db.operations.guest
- app.db.operations.client
"""

# Re-export all operations from the modular structure
from .operations import *

# Maintain backward compatibility
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
    # Chat - Legacy
    "fetch_all_chats",
    "save_chat",
    "delete_all_chats",
    # Message
    "fetch_messages",
    "save_message",
    "get_messages_by_chat",
    # Message - Legacy
    "fetch_messages_old",
    "save_message_old",
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