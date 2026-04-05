"""
LLM, embedding, and API key management.

Consolidates provider initialization — creates LLM instances, embedding
functions, and validates that required API keys are present.
"""

from typing import Dict, List

from langchain_cohere.embeddings import CohereEmbeddings
from langchain_groq import ChatGroq

from app.core.config import settings


# ---------------------------------------------------------------------------
# Model mapping
# ---------------------------------------------------------------------------

GROQ_MODEL_MAP: Dict[str, str] = {
    "Llama-instant": "llama-3.1-8b-instant",
    "Llama-large": "llama-3.3-70b-versatile",
    "GPT-OSS-120B": "openai/gpt-oss-120b",
    "GPT-OSS-20B": "openai/gpt-oss-20b",
    "Groq": "llama-3.1-8b-instant",  # legacy alias
}

GROQ_MODELS = set(GROQ_MODEL_MAP.keys())

ALL_MODELS: List[str] = [
    "Llama-instant", "Llama-large", "GPT-OSS-120B", "GPT-OSS-20B",
    "GPT-4o-mini", "GPT-4o", "GPT-4.1", "GPT-4.1-mini",
]


def get_available_models() -> List[str]:
    return list(ALL_MODELS)


# ---------------------------------------------------------------------------
# API key helpers — thin wrappers kept for readability in callers
# ---------------------------------------------------------------------------

def _require(value, name: str) -> str:
    if not value:
        raise ValueError(f"{name} API key is not set in environment variables.")
    return value


def get_groq_api_key() -> str:
    return settings.groq_api_key or ""

def get_openai_api_key() -> str:
    return settings.openai_api_key or ""


def get_pinecone_api_key() -> str:
    return settings.pinecone_api_key or ""


# ---------------------------------------------------------------------------
# Embedding factory
# ---------------------------------------------------------------------------

def create_embedding_function() -> CohereEmbeddings:
    """Create Cohere embeddings function."""
    _require(settings.cohere_api_key, "Cohere")
    return CohereEmbeddings(
        model=settings.embedding_model, cohere_api_key=settings.cohere_api_key
    )


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def create_llm(llm_model: str = "Llama-instant"):
    """Create a language model instance for the given model name."""
    if llm_model in GROQ_MODEL_MAP:
        key = _require(settings.groq_api_key, "Groq")
        return ChatGroq(
            model=GROQ_MODEL_MAP[llm_model], api_key=key, temperature=0.7
        )

    if llm_model == "GPT-4o-mini":
        key = _require(settings.openai_api_key, "OpenAI")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", api_key=key, temperature=0.7)

    if llm_model == "GPT-4o":
        key = _require(settings.openai_api_key, "OpenAI")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", api_key=key, temperature=0.7)

    if llm_model == "GPT-4.1":
        key = _require(settings.openai_api_key, "OpenAI")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4.1", api_key=key, temperature=0.7)

    if llm_model == "GPT-4.1-mini":
        key = _require(settings.openai_api_key, "OpenAI")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4.1-mini", api_key=key, temperature=0.7)

    raise ValueError(
        f"Model '{llm_model}' not available. Available: {', '.join(ALL_MODELS)}"
    )
