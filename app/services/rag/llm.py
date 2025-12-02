"""
Language model initialization.
"""

from typing import Dict
from langchain_groq import ChatGroq
from .api_keys import check_groq_key, get_groq_api_key, check_openai_key, get_openai_api_key


# Model mapping: friendly name -> actual Groq model ID
GROQ_MODEL_MAP: Dict[str, str] = {
    "Llama-instant": "llama-3.1-8b-instant",
    "Llama-large": "llama-3.3-70b-versatile",
    "Mixtral": "mixtral-8x7b-32768",
    "Gemma": "gemma2-9b-it",
    "Qwen": "qwen-32b-preview",
    # Legacy support
    "Groq": "llama-3.1-8b-instant",  # Default to instant model
}


def get_available_models():
    """
    Get list of all available models.

    Returns:
        List of model names
    """
    return list(GROQ_MODEL_MAP.keys()) + ["OpenAI"]


def create_llm(llm_model: str = "Llama-instant"):
    """
    Create a language model instance.

    Args:
        llm_model: Model name to use. Options:
            - "Llama-instant": Fast, efficient Llama 3.1 8B
            - "Llama-large": Powerful Llama 3.3 70B
            - "Mixtral": Mixtral 8x7B MoE model
            - "Gemma": Google Gemma 2 9B
            - "Qwen": Qwen 32B model
            - "OpenAI": OpenAI GPT models
            - "Groq": Legacy, defaults to Llama-instant

    Returns:
        LLM instance

    Raises:
        ValueError: If model is not supported
    """
    # Check if it's a Groq model
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
            openai_api_key=openai_api_key,
            temperature=0.7
        )

    else:
        available = ", ".join(get_available_models())
        raise ValueError(
            f"Model '{llm_model}' not available. Available models: {available}"
        )