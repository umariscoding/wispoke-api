from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from typing import List, BinaryIO
import tempfile
import os
from pathlib import Path
from app.core.config import settings
from supabase import create_client

# Initialize Supabase client for storage
def get_supabase_storage_client():
    """Get Supabase client for storage operations."""
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("Supabase URL and Key must be configured")
    return create_client(settings.supabase_url, settings.supabase_key)

# Supabase bucket name for documents
DOCUMENTS_BUCKET = "documents"

def split_text_for_txt(documents):
    """Split the provided text into optimized chunks for RAG performance.

    Args:
        documents (str): The text to be split.

    Returns:
        list: A list of text chunks.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,      # Reduced from 1000 for faster processing
        chunk_overlap=100,   # Reduced from 200 for better performance
        length_function=len,
        separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]  # Better separators
    )
    return text_splitter.split_text(documents)

async def upload_file_to_supabase(
    file_content: bytes,
    filename: str,
    company_id: str,
    doc_id: str
) -> str:
    """
    Upload a file to Supabase storage.

    Args:
        file_content: Binary file content
        filename: Original filename
        company_id: Company ID for organization
        doc_id: Document ID for unique identification

    Returns:
        str: Public URL of the uploaded file
    """
    try:
        supabase = get_supabase_storage_client()

        # Create a unique path: company_id/doc_id/filename
        file_path = f"{company_id}/{doc_id}/{filename}"

        # Ensure bucket exists with public access and no RLS
        try:
            bucket = supabase.storage.get_bucket(DOCUMENTS_BUCKET)
        except:
            # Create bucket if it doesn't exist with public access
            try:
                supabase.storage.create_bucket(
                    DOCUMENTS_BUCKET,
                    options={
                        "public": True,
                        "file_size_limit": 52428800,  # 50MB
                        "allowed_mime_types": [
                            "application/pdf",
                            "text/plain",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "application/msword"
                        ]
                    }
                )
            except Exception as create_error:
                # Bucket might already exist, continue
                pass

        # Upload file with upsert to overwrite if exists
        try:
            supabase.storage.from_(DOCUMENTS_BUCKET).upload(
                file_path,
                file_content,
                file_options={
                    "content-type": get_content_type(filename),
                    "upsert": "true"
                }
            )
        except Exception as upload_error:
            # If upload fails, try to remove existing file and upload again
            try:
                supabase.storage.from_(DOCUMENTS_BUCKET).remove([file_path])
            except:
                pass

            supabase.storage.from_(DOCUMENTS_BUCKET).upload(
                file_path,
                file_content,
                file_options={"content-type": get_content_type(filename)}
            )

        # Get public URL
        file_url = supabase.storage.from_(DOCUMENTS_BUCKET).get_public_url(file_path)

        return file_url

    except Exception as e:
        raise Exception(f"Failed to upload file to Supabase: {str(e)}")

def get_content_type(filename: str) -> str:
    """Get content type based on file extension."""
    extension = Path(filename).suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword"
    }
    return content_types.get(extension, "application/octet-stream")

async def extract_text_from_file(
    file_content: bytes,
    filename: str,
    content_type: str
) -> str:
    """
    Extract text content from various file types using LangChain loaders.

    Args:
        file_content: Binary file content
        filename: Original filename
        content_type: MIME type of the file

    Returns:
        str: Extracted text content
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

        elif extension == ".docx" or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            loader = Docx2txtLoader(temp_file_path)
            documents = loader.load()
            text_content = "\n\n".join([doc.page_content for doc in documents])

        elif extension == ".txt" or content_type.startswith("text/"):
            loader = TextLoader(temp_file_path, encoding='utf-8')
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
        bool: True if file type is supported
    """
    extension = Path(filename).suffix.lower()
    supported_extensions = [".pdf", ".txt", ".docx"]
    supported_content_types = [
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]

    return (
        extension in supported_extensions or
        content_type in supported_content_types or
        content_type.startswith("text/")
    )

def get_file_extension_from_content_type(content_type: str) -> str:
    """Get file extension from content type."""
    type_mapping = {
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"
    }
    return type_mapping.get(content_type, ".txt")