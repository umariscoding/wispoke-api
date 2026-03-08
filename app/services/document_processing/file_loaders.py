"""
File loading utilities for extracting text from various file formats.
"""

import os
import tempfile
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader


async def extract_text_from_file(
    file_content: bytes, filename: str, content_type: str
) -> str:
    """
    Extract text content from various file types using LangChain loaders.

    Args:
        file_content: Binary file content
        filename: Original filename
        content_type: MIME type of the file

    Returns:
        Extracted text content
    """
    # Get file extension
    extension = Path(filename).suffix.lower()

    # Create a temporary file to store the uploaded content
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    try:
        # Load document based on file type
        if extension == ".pdf" or content_type == "application/pdf":
            loader = PyPDFLoader(temp_file_path)
            documents = loader.load()
            text_content = "\n\n".join([doc.page_content for doc in documents])

        elif (
            extension == ".docx"
            or content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            loader = Docx2txtLoader(temp_file_path)
            documents = loader.load()
            text_content = "\n\n".join([doc.page_content for doc in documents])

        elif extension == ".txt" or content_type.startswith("text/"):
            loader = TextLoader(temp_file_path, encoding="utf-8")
            documents = loader.load()
            text_content = "\n\n".join([doc.page_content for doc in documents])

        else:
            raise ValueError(f"Unsupported file type: {extension}")

        return text_content

    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def validate_file_type(filename: str, content_type: str) -> bool:
    """
    Validate if the file type is supported.

    Args:
        filename: Original filename
        content_type: MIME type of the file

    Returns:
        True if file type is supported
    """
    extension = Path(filename).suffix.lower()
    supported_extensions = [".pdf", ".txt", ".docx"]
    supported_content_types = [
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    return (
        extension in supported_extensions
        or content_type in supported_content_types
        or content_type.startswith("text/")
    )


def get_file_extension_from_content_type(content_type: str) -> str:
    """
    Get file extension from content type.

    Args:
        content_type: MIME type

    Returns:
        File extension
    """
    type_mapping = {
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    return type_mapping.get(content_type, ".txt")