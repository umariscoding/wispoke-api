"""
Manual chain implementations for RAG system.
Provides separate chains for question contextualization and answer generation.
"""

from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langsmith import traceable
from .prompts import (
    contextualize_system_prompt,
    contextualize_user_prompt,
    qa_system_prompt,
    qa_user_prompt,
)


def format_chat_history_for_contextualization(messages: List[BaseMessage]) -> str:
    """
    Format chat history for the contextualization prompt.
    Takes all available messages.

    Args:
        messages: List of message objects from chat history

    Returns:
        Formatted string representation of chat history
    """
    if not messages:
        return "No previous conversation."

    formatted_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            formatted_messages.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            formatted_messages.append(f"Assistant: {msg.content}")

    return "\n".join(formatted_messages)


def format_chat_history_for_qa(messages: List[BaseMessage]) -> str:
    """
    Format chat history for the QA prompt.
    Only takes the last 5 messages to keep context focused.

    Args:
        messages: List of message objects from chat history

    Returns:
        Formatted string representation of last 5 messages
    """
    if not messages:
        return "No previous conversation in this session."

    # Take only last 5 messages (last 2-3 exchanges)
    recent_messages = messages[-5:]

    formatted_messages = []
    for msg in recent_messages:
        if isinstance(msg, HumanMessage):
            formatted_messages.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            formatted_messages.append(f"Assistant: {msg.content}")

    if len(messages) > 5:
        return (
            f"[Earlier messages omitted - showing last 5 messages]\n\n"
            + "\n".join(formatted_messages)
        )
    else:
        return "\n".join(formatted_messages)


@traceable(name="create_contextualization_chain")
def create_contextualization_chain(llm):
    """
    Create a chain that reformulates questions based on chat history.
    This makes follow-up questions standalone.

    Args:
        llm: Language model instance

    Returns:
        Runnable chain for question contextualization
    """
    # Create prompt template
    prompt = ChatPromptTemplate.from_messages(
        [("system", contextualize_system_prompt), ("user", contextualize_user_prompt)]
    )

    # Create chain: prompt -> llm -> output parser
    chain = (
        {
            "chat_history": lambda x: format_chat_history_for_contextualization(
                x["chat_history"]
            ),
            "input": lambda x: x["input"],
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain


@traceable(name="create_retrieval_chain")
def create_retrieval_chain(retriever, contextualization_chain):
    """
    Create a chain that retrieves relevant documents.
    Uses the contextualized question for better retrieval.

    Args:
        retriever: Document retriever instance
        contextualization_chain: Chain for contextualizing questions

    Returns:
        Runnable chain for document retrieval
    """

    def contextualize_if_needed(inputs: Dict[str, Any]) -> str:
        """
        Contextualize question only if there's chat history.
        Otherwise, use the original question.
        """
        chat_history = inputs.get("chat_history", [])

        # If no chat history, return original question
        if not chat_history:
            return inputs["input"]

        # Otherwise, contextualize the question
        return contextualization_chain.invoke(
            {"chat_history": chat_history, "input": inputs["input"]}
        )

    # Create retrieval chain
    chain = RunnableLambda(contextualize_if_needed) | retriever

    return chain


@traceable(name="create_qa_chain")
def create_qa_chain(llm, retriever, contextualization_chain, company_context: Dict[str, str]):
    """
    Create the complete QA chain that:
    1. Contextualizes the question (if needed)
    2. Retrieves relevant documents
    3. Generates an answer using context and last 5 messages

    Args:
        llm: Language model instance
        retriever: Document retriever instance
        contextualization_chain: Chain for contextualizing questions
        company_context: Dictionary with company info (name, email, description)

    Returns:
        Runnable chain for complete QA process
    """
    # Create retrieval chain
    retrieval_chain = create_retrieval_chain(retriever, contextualization_chain)

    # Create QA prompt template with company context
    qa_prompt = ChatPromptTemplate.from_messages(
        [("system", qa_system_prompt), ("user", qa_user_prompt)]
    )

    def format_documents(docs):
        """Format retrieved documents into a single context string."""
        if not docs:
            return "No relevant documents found in the knowledge base."
        return "\n\n".join(
            [f"Document {i+1}:\n{doc.page_content}" for i, doc in enumerate(docs)]
        )

    def prepare_qa_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare inputs for the QA chain.
        Retrieves documents and formats chat history (last 5 messages).
        """
        # Get retrieved documents
        retrieved_docs = retrieval_chain.invoke(inputs)

        # Format context from documents
        context = format_documents(retrieved_docs)

        # Format chat history (last 5 messages only)
        chat_history = format_chat_history_for_qa(inputs.get("chat_history", []))

        return {
            "context": context,
            "chat_history": chat_history,
            "input": inputs["input"],
            "company_name": company_context.get("company_name", "our company"),
            "company_email": company_context.get("company_email", "support@company.com"),
            "company_description": company_context.get("company_description", ""),
        }

    # Create complete QA chain
    chain = RunnableLambda(prepare_qa_inputs) | qa_prompt | llm | StrOutputParser()

    return chain


@traceable(name="create_conversational_rag_chain")
def create_conversational_rag_chain(llm, retriever, company_context: Dict[str, str]):
    """
    Create the complete conversational RAG chain.
    This is the main chain that combines all components.

    Args:
        llm: Language model instance
        retriever: Document retriever instance
        company_context: Dictionary with company info (name, email, description)

    Returns:
        Complete conversational RAG chain
    """
    # Create contextualization chain
    contextualization_chain = create_contextualization_chain(llm)

    # Create QA chain with company context
    qa_chain = create_qa_chain(llm, retriever, contextualization_chain, company_context)

    return qa_chain