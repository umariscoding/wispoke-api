"""
Response streaming for RAG chains.
"""

from typing import AsyncGenerator
from .rag_chain import get_company_rag_chain
from .api_keys import (
    get_groq_api_key,
    get_openai_api_key,
    get_cohere_api_key,
    get_anthropic_api_key,
    get_pinecone_api_key
)


async def stream_company_response(
    company_id: str, query: str, chat_id: str, llm_model: str = "Llama-instant"
) -> AsyncGenerator[str, None]:
    """
    Stream response from company-specific RAG chain.

    Args:
        company_id: Company ID
        query: User query
        chat_id: Chat ID
        llm_model: LLM model to use (default: Llama-instant)

    Yields:
        Response chunks
    """
    try:
        # Check API keys based on the model
        # Llama models (Llama-instant, Llama-large) and legacy "Groq" use Groq API
        if llm_model in ["Groq", "Llama-instant", "Llama-large"]:
            groq_key = get_groq_api_key()
            if not groq_key or groq_key == "your-groq-api-key-here":
                yield "Error: Groq API key not configured. Please create a .env file in the project root and set GROQ_API_KEY=your-actual-groq-key. You can get an API key from https://console.groq.com/"
                return
        elif llm_model == "OpenAI":
            openai_key = get_openai_api_key()
            if not openai_key or openai_key == "your-openai-api-key-here":
                yield "Error: OpenAI API key not configured. Please create a .env file in the project root and set OPENAI_API_KEY=your-actual-openai-key. You can get an API key from https://platform.openai.com/api-keys"
                return
        elif llm_model == "Claude":
            anthropic_key = get_anthropic_api_key()
            if not anthropic_key or anthropic_key == "your-anthropic-api-key-here":
                yield "Error: Anthropic API key not configured. Please create a .env file in the project root and set ANTHROPIC_API_KEY=your-actual-anthropic-key. You can get an API key from https://console.anthropic.com/"
                return
        elif llm_model == "Cohere":
            cohere_key = get_cohere_api_key()
            if not cohere_key or cohere_key == "your-cohere-api-key-here":
                yield "Error: Cohere API key not configured. Please create a .env file in the project root and set COHERE_API_KEY=your-actual-cohere-key. You can get an API key from https://cohere.com/"
                return

        # Check if Pinecone API key is available
        pinecone_key = get_pinecone_api_key()
        if not pinecone_key or pinecone_key == "your-pinecone-api-key-here":
            yield "Error: Pinecone API key not configured. Please create a .env file in the project root and set PINECONE_API_KEY=your-actual-pinecone-key. You can get an API key from https://pinecone.io/"
            return

        # Get company-specific RAG chain
        try:
            rag_chain = await get_company_rag_chain(company_id, llm_model)
        except Exception as chain_error:
            error_msg = str(chain_error)

            # Provide specific error messages
            if "unsupported operand" in error_msg.lower():
                yield "Error: Internal retriever compatibility issue. Please try again or contact support."
            elif "pinecone" in error_msg.lower():
                yield "Error: Knowledge base connection failed. Please ensure documents are uploaded."
            elif (
                "groq" in error_msg.lower()
                or "openai" in error_msg.lower()
                or "api" in error_msg.lower()
            ):
                yield "Error: AI service connection failed. Please check API configuration."
            else:
                yield f"Error: Failed to initialize chat system. Details: {error_msg}"
            return

        # Stream response
        try:
            resp = rag_chain.stream(
                {"input": query},
                config={"configurable": {"session_id": chat_id}},
            )

            response_started = False

            for chunk in resp:
                # The manual chains return the response directly as a string
                if isinstance(chunk, str):
                    response_started = True
                    if chunk:
                        yield chunk
                # Fallback for dict format (backward compatibility)
                elif isinstance(chunk, dict) and "answer" in chunk:
                    response_started = True
                    chunk_content = chunk["answer"]
                    if chunk_content:
                        yield chunk_content

            # If no response was generated
            if not response_started:
                yield "I apologize, but I couldn't generate a response. Please try again or contact support if the issue persists."

        except Exception as stream_error:
            yield f"Error: Failed to generate response. Details: {str(stream_error)}"
            return

    except Exception as e:
        error_msg = str(e)
        if "api key" in error_msg.lower() or "unauthorized" in error_msg.lower():
            yield "Error: Invalid or missing API key. Please check your API key configuration."
        elif "pinecone" in error_msg.lower():
            yield "Error: Pinecone connection failed. Please check your Pinecone API key configuration."
        else:
            yield f"Error: {error_msg}"