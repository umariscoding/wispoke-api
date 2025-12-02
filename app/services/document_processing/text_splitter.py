"""
Text splitting utilities for document processing.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text_for_txt(documents: str) -> list:
    """
    Split the provided text into optimized chunks for RAG performance.

    Args:
        documents: The text to be split.

    Returns:
        A list of text chunks.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,  # Reduced from 1000 for faster processing
        chunk_overlap=100,  # Reduced from 200 for better performance
        length_function=len,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            ", ",
            " ",
            "",
        ],  # Better separators
    )
    return text_splitter.split_text(documents)