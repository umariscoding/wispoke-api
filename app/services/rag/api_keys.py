"""
API key validation and retrieval functions.
"""

from app.core.config import settings


def check_openai_key():
    """Validate OpenAI API key is set."""
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is not set in the environment variables.")


def check_cohere_key():
    """Validate Cohere API key is set."""
    if not settings.cohere_api_key:
        raise ValueError("Cohere API key is not set in the environment variables.")


def check_groq_key():
    """Validate Groq API key is set."""
    if not settings.groq_api_key:
        raise ValueError("Groq API key is not set in the environment variables.")


def check_anthropic_key():
    """Validate Anthropic API key is set."""
    if not settings.anthropic_api_key:
        raise ValueError("Anthropic API key is not set in the environment variables.")


def check_pinecone_key():
    """Validate Pinecone API key is set."""
    if not settings.pinecone_api_key:
        raise ValueError("Pinecone API key is not set in the environment variables.")


def get_openai_api_key() -> str:
    """Get the current OpenAI API key from settings."""
    return settings.openai_api_key


def get_cohere_api_key() -> str:
    """Get the current Cohere API key from settings."""
    return settings.cohere_api_key


def get_anthropic_api_key() -> str:
    """Get the current Anthropic API key from settings."""
    return settings.anthropic_api_key


def get_groq_api_key() -> str:
    """Get the current Groq API key from settings."""
    return settings.groq_api_key


def get_pinecone_api_key() -> str:
    """Get the current Pinecone API key from settings."""
    return settings.pinecone_api_key