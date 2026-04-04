"""
RAG chain — building, caching, and management.

Combines question contextualization, document retrieval, QA generation,
and session-history wrapping into a single conversational RAG chain per company.
Includes TTL-based caching.
"""

import time
import logging
from typing import List, Dict, Any, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

from .prompts import (
    contextualize_system_prompt,
    contextualize_user_prompt,
    qa_system_prompt,
    qa_user_prompt,
)
from .providers import create_llm, create_embedding_function
from .pinecone_client import get_pinecone_client, get_shared_index_name, ensure_shared_index_exists
from .retriever import create_company_retriever
from .vector_store import clear_vector_store_cache, get_vector_store_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 3600  # 1 hour
_company_rag_chains: Dict[str, Dict[str, Tuple[RunnableWithMessageHistory, float]]] = {}


def _is_expired(created_at: float) -> bool:
    return (time.time() - created_at) > _CACHE_TTL_SECONDS


def get_rag_chain_cache() -> Dict[str, Dict[str, Any]]:
    return _company_rag_chains


def clear_company_rag_chain_cache(company_id: str) -> None:
    _company_rag_chains.pop(company_id, None)


def clear_rag_chain_cache() -> None:
    _company_rag_chains.clear()


def clear_company_cache(company_id: str) -> None:
    """Clear all cached data (vector stores + chains) for a company."""
    get_vector_store_cache().pop(company_id, None)
    _company_rag_chains.pop(company_id, None)


def clear_all_cache() -> None:
    """Clear all cached data across all companies."""
    clear_vector_store_cache()
    clear_rag_chain_cache()


# ---------------------------------------------------------------------------
# History formatting
# ---------------------------------------------------------------------------

def _format_history_full(messages: List[BaseMessage]) -> str:
    if not messages:
        return "No previous conversation."
    parts = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            parts.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            parts.append(f"Assistant: {msg.content}")
    return "\n".join(parts)


def _format_history_recent(messages: List[BaseMessage], limit: int = 5) -> str:
    if not messages:
        return "No previous conversation in this session."
    recent = messages[-limit:]
    parts = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            parts.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            parts.append(f"Assistant: {msg.content}")
    text = "\n".join(parts)
    if len(messages) > limit:
        text = f"[Earlier messages omitted - showing last {limit} messages]\n\n{text}"
    return text


# ---------------------------------------------------------------------------
# Chain building
# ---------------------------------------------------------------------------

_TONE_MAP = {
    "professional": "## TONE & STYLE\n\nYou MUST be friendly but professional. Be helpful, clear, confident, and polite. Use natural customer-service warmth.",
    "friendly": "## TONE & STYLE\n\nYou MUST use a warm, friendly, and approachable tone in EVERY response. Be enthusiastic, use casual language, add exclamation marks, and sound genuinely excited to help! Never sound robotic or formal.",
    "casual": "## TONE & STYLE\n\nYou MUST use a very casual, relaxed tone in EVERY response. Talk like a friend would \u2014 use contractions, simple language, and be laid-back. Never sound corporate or stiff.",
    "formal": "## TONE & STYLE\n\nYou MUST use a formal, polished tone in EVERY response. Be precise, use proper grammar, avoid contractions, and maintain a corporate-level professionalism throughout.",
    "witty": "## TONE & STYLE\n\nYou MUST use a witty, clever tone in EVERY response. Add humor, wordplay, puns, or clever observations. Be playful and entertaining while still being helpful. Never be dry or boring.",
}


def _build_chain(llm, retriever, company_context: Dict[str, str]):
    """Build the full contextualization -> retrieval -> QA pipeline."""

    # --- Contextualization chain ---
    ctx_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_system_prompt),
        ("user", contextualize_user_prompt),
    ])
    ctx_chain = (
        {
            "chat_history": lambda x: _format_history_full(x["chat_history"]),
            "input": lambda x: x["input"],
        }
        | ctx_prompt | llm | StrOutputParser()
    )

    # --- Retrieval chain ---
    def _contextualize_if_needed(inputs: Dict[str, Any]) -> str:
        if not inputs.get("chat_history"):
            return inputs["input"]
        return ctx_chain.invoke({"chat_history": inputs["chat_history"], "input": inputs["input"]})

    retrieval_chain = RunnableLambda(_contextualize_if_needed) | retriever

    # --- QA chain ---
    tone = company_context.get("tone", "professional")
    tone_block = _TONE_MAP.get(tone, _TONE_MAP["professional"])
    logger.info("Building chain with tone=%s for company context: %s", tone, company_context.get("company_name"))
    custom_prompt = company_context.get("custom_system_prompt", "")
    if custom_prompt:
        custom_prompt = custom_prompt.replace("{", "{{").replace("}", "}}")
        tone_block += f"\n\n## ADDITIONAL INSTRUCTIONS (MUST FOLLOW)\n\n{custom_prompt}"

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        ("user", qa_user_prompt),
    ])

    def _format_docs(docs):
        if not docs:
            return "No relevant documents found in the knowledge base."
        return "\n\n".join(f"Document {i+1}:\n{d.page_content}" for i, d in enumerate(docs))

    def _prepare_qa(inputs: Dict[str, Any]) -> Dict[str, Any]:
        docs = retrieval_chain.invoke(inputs)
        return {
            "context": _format_docs(docs),
            "chat_history": _format_history_recent(inputs.get("chat_history", [])),
            "input": inputs["input"],
            "company_name": company_context.get("company_name", "our company"),
            "company_email": company_context.get("company_email", "support@company.com"),
            "company_description": company_context.get("company_description", ""),
            "tone_instruction": tone_block,
        }

    return RunnableLambda(_prepare_qa) | qa_prompt | llm | StrOutputParser()


# ---------------------------------------------------------------------------
# Public API — get (or build + cache) a company's chain
# ---------------------------------------------------------------------------

def get_company_rag_chain(
    company_id: str, llm_model: str = "Llama-instant"
) -> RunnableWithMessageHistory:
    """
    Get or create a company-specific conversational RAG chain.
    Cached with 1-hour TTL.
    """
    global _company_rag_chains

    from app.features.auth.repository import get_company_by_id
    from app.features.chat.repository import load_session_history

    if company_id not in _company_rag_chains:
        _company_rag_chains[company_id] = {}

    company = get_company_by_id(company_id)

    # Plan gating: free users get default model, tone, and no custom prompt
    from app.features.billing.service import is_plan_active
    plan_active = company and is_plan_active(company)

    resolved_model = "Llama-large"
    if company and plan_active:
        resolved_model = company.get("default_model") or "Llama-large"

    # Cache key includes plan status so chains are rebuilt on plan changes
    cache_key = f"{resolved_model}:{'pro' if plan_active else 'free'}"

    # Cache hit?
    if cache_key in _company_rag_chains[company_id]:
        chain, created_at = _company_rag_chains[company_id][cache_key]
        if not _is_expired(created_at):
            return chain
        del _company_rag_chains[company_id][cache_key]

    # Build
    company_context = {
        "company_name": company.get("name", "our company") if company else "our company",
        "company_email": company.get("email", "support@company.com") if company else "support@company.com",
        "company_description": "",
        "custom_system_prompt": company.get("system_prompt", "") if plan_active else "",
        "tone": company.get("tone", "professional") if plan_active else "professional",
    }
    if company and company.get("chatbot_description"):
        company_context["company_description"] = f"- Description: {company['chatbot_description']}"

    ensure_shared_index_exists()
    index_name = get_shared_index_name()
    embedding_fn = create_embedding_function()
    pinecone_index = get_pinecone_client().Index(index_name)
    # Free users can only retrieve text-uploaded documents, not Pro file uploads
    rag_filter = {"upload_source": {"$eq": "text"}} if not plan_active else None
    retriever = create_company_retriever(pinecone_index, embedding_fn, namespace=company_id, metadata_filter=rag_filter)
    llm = create_llm(resolved_model)

    rag_chain = _build_chain(llm, retriever, company_context)

    def get_session_history(chat_id: str) -> BaseChatMessageHistory:
        try:
            return load_session_history(company_id, chat_id)
        except Exception:
            from langchain_core.chat_history import InMemoryChatMessageHistory
            return InMemoryChatMessageHistory()

    conversational_chain = RunnableWithMessageHistory(
        rag_chain, get_session_history,
        input_messages_key="input", history_messages_key="chat_history",
    )


    return conversational_chain
