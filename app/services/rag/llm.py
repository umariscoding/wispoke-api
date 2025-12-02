"""
Language model initialization.
"""

from langchain_groq import ChatGroq
from .api_keys import check_groq_key, get_groq_api_key, check_openai_key, get_openai_api_key


def create_llm(llm_model: str = "Groq"):
    """
    Create a language model instance.

    Args:
        llm_model: Model type to use ("Groq" or "OpenAI")

    Returns:
        LLM instance

    Raises:
        ValueError: If model is not supported
    """
    if llm_model == "Groq":
        check_groq_key()
        groq_api_key = get_groq_api_key()
        return ChatGroq(
            model="llama-3.1-8b-instant", api_key=groq_api_key, temperature=0.7
        )
    elif llm_model == "OpenAI":
        check_openai_key()
        openai_api_key = get_openai_api_key()
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(openai_api_key=openai_api_key)
    else:
        raise ValueError(
            f"Model {llm_model} not available. Only Groq and OpenAI are supported."
        )