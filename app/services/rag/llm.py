"""
Language model initialization.
"""

from typing import Dict
from langchain_groq import ChatGroq
from .api_keys import (
    check_groq_key, get_groq_api_key,
    check_openai_key, get_openai_api_key,
    check_cohere_key, get_cohere_api_key,
    check_anthropic_key, get_anthropic_api_key
)


# Model mapping: friendly name -> actual model ID
GROQ_MODEL_MAP: Dict[str, str] = {
    "Llama-instant": "llama-3.1-8b-instant",
    "Llama-large": "llama-3.3-70b-versatile",
    # Legacy support
    "Groq": "llama-3.1-8b-instant",  # Default to instant model
}


def get_available_models():
    """
    Get list of all available models.

    Returns:
        List of model names
    """
    return ["Llama-instant", "Llama-large", "OpenAI", "Claude", "Cohere"]


def create_llm(llm_model: str = "Llama-instant"):
    """
    Create a language model instance.

    Args:
        llm_model: Model name to use. Options:
            - "Llama-instant": Fast Llama 3.1 8B (via Groq)
            - "Llama-large": Powerful Llama 3.3 70B (via Groq)
            - "OpenAI": OpenAI GPT-4 models
            - "Claude": Anthropic Claude models
            - "Cohere": Cohere Command models
            - "Groq": Legacy, defaults to Llama-instant

    Returns:
        LLM instance

    Raises:
        ValueError: If model is not supported
    """
    # Check if it's a Groq model (Llama models)
    if llm_model in GROQ_MODEL_MAP:
        check_groq_key()
        groq_api_key = get_groq_api_key()
        actual_model_id = GROQ_MODEL_MAP[llm_model]

        return ChatGroq(
            model=actual_model_id,
            api_key=groq_api_key,
            temperature=0.7
        )

    # OpenAI model
    elif llm_model == "OpenAI":
        check_openai_key()
        openai_api_key = get_openai_api_key()
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="gpt-4o-mini",  # Using GPT-4o-mini for cost-efficiency
            api_key=openai_api_key,
            temperature=0.7
        )

    # Claude (Anthropic) model
    elif llm_model == "Claude":
        check_anthropic_key()
        anthropic_api_key = get_anthropic_api_key()
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model="claude-3-5-sonnet-20241022",  # Using Claude 3.5 Sonnet
            api_key=anthropic_api_key,
            temperature=0.7
        )

    # Cohere model
    elif llm_model == "Cohere":
        check_cohere_key()
        cohere_api_key = get_cohere_api_key()
        from langchain_cohere import ChatCohere

        return ChatCohere(
            model="command-a-03-2025",  # Using Command R+ model
            cohere_api_key=cohere_api_key,
            temperature=0.7
        )

    else:
        available = ", ".join(get_available_models())
        raise ValueError(
            f"Model '{llm_model}' not available. Available models: {available}"
        )