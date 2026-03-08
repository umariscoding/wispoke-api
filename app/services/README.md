# Services Module Structure

This document explains the modular structure of the services directory and how to use the different modules.

## Overview

The services directory has been refactored into smaller, focused modules for better maintainability and organization. The refactoring maintains backward compatibility through re-export layers.

## Directory Structure

```
app/services/
├── rag/                          # RAG (Retrieval-Augmented Generation) module
│   ├── __init__.py              # Exports all RAG functions
│   ├── api_keys.py              # API key validation and retrieval
│   ├── pinecone_client.py       # Pinecone initialization and management
│   ├── embeddings.py            # Cohere embedding functions
│   ├── vector_store.py          # Vector store operations and caching
│   ├── retriever.py             # Custom document retriever
│   ├── llm.py                   # LLM creation (Groq/OpenAI)
│   ├── rag_chain.py             # RAG chain creation and caching
│   ├── streaming.py             # Response streaming logic
│   ├── document_processor.py    # Document processing for vector store
│   ├── cache.py                 # Cache management functions
│   ├── chains.py                # Manual chain implementations
│   └── prompts.py               # Prompt templates
├── document_processing/          # Document processing module
│   ├── __init__.py              # Exports all document processing functions
│   ├── text_splitter.py         # Text splitting and chunking
│   ├── file_loaders.py          # File loading and text extraction
│   └── storage.py               # Supabase storage operations
├── langchain_service.py          # Backward compatibility layer for RAG
└── document_service.py           # Backward compatibility layer for documents
```

## Module Details

### RAG Module (`app/services/rag/`)

The RAG module handles all Retrieval-Augmented Generation functionality.

#### API Keys (`api_keys.py`)
Validates and retrieves API keys for different services.

**Functions:**
- `check_groq_key()` - Validate Groq API key exists
- `get_groq_api_key()` - Get Groq API key
- `check_openai_key()` - Validate OpenAI API key exists
- `get_openai_api_key()` - Get OpenAI API key
- `check_pinecone_key()` - Validate Pinecone API key exists
- `get_pinecone_api_key()` - Get Pinecone API key

#### Pinecone Client (`pinecone_client.py`)
Manages Pinecone vector database connections.

**Functions:**
- `get_pinecone_client()` - Get singleton Pinecone client
- `ensure_base_index_exists()` - Ensure base multi-tenant index exists
- `get_company_namespace(company_id)` - Get company-specific namespace
- `BASE_INDEX_NAME` - Base index name constant

#### Embeddings (`embeddings.py`)
Creates Cohere embedding functions.

**Functions:**
- `create_embedding_function()` - Create Cohere embeddings instance

#### Vector Store (`vector_store.py`)
Manages vector store operations and caching.

**Functions:**
- `get_company_vector_store(company_id)` - Get or create company vector store
- `get_vector_store_cache()` - Get vector store cache
- `clear_vector_store_cache()` - Clear all vector store cache

#### Retriever (`retriever.py`)
Custom document retriever implementation.

**Classes:**
- `DirectPineconeRetriever` - Custom retriever with direct Pinecone queries

**Functions:**
- `create_company_retriever(index, embedding_fn, namespace)` - Create retriever instance

#### LLM (`llm.py`)
Creates language model instances.

**Functions:**
- `create_llm(llm_model)` - Create LLM (supports "Groq" and "OpenAI")

#### RAG Chain (`rag_chain.py`)
Creates and manages RAG chains with caching.

**Functions:**
- `get_company_rag_chain(company_id, llm_model)` - Get or create RAG chain (cached)
- `get_rag_chain_cache()` - Get RAG chain cache
- `clear_rag_chain_cache()` - Clear RAG chain cache

#### Streaming (`streaming.py`)
Handles response streaming from RAG chains.

**Functions:**
- `stream_company_response(company_id, query, chat_id, llm_model)` - Stream responses

#### Document Processor (`document_processor.py`)
Processes documents for the knowledge base.

**Functions:**
- `process_company_document(company_id, content, doc_id)` - Process and embed document

#### Cache (`cache.py`)
Cache management utilities.

**Functions:**
- `clear_company_cache(company_id)` - Clear cache for specific company
- `clear_all_cache()` - Clear all cached data
- `clear_cache()` - Legacy function for clearing cache
- `force_refresh_all_rag_chains()` - Legacy function for refreshing chains

#### Chains (`chains.py`)
Manual chain implementations with LangSmith tracing.

**Functions:**
- `create_conversational_rag_chain(llm, retriever)` - Main conversational RAG chain
- `create_contextualization_chain(llm)` - Question reformulation chain
- `create_retrieval_chain(retriever, contextualization_chain)` - Document retrieval chain
- `create_qa_chain(llm, retriever, contextualization_chain)` - QA chain
- `format_chat_history_for_contextualization(messages)` - Format all messages
- `format_chat_history_for_qa(messages)` - Format last 5 messages

**Key Features:**
- Contextualization uses ALL chat history for better understanding
- Final answer only uses LAST 5 MESSAGES to reduce token usage
- All chains have `@traceable` decorator for LangSmith monitoring

#### Prompts (`prompts.py`)
Prompt templates for RAG system.

**Variables:**
- `contextualize_system_prompt` - System prompt for question reformulation
- `contextualize_user_prompt` - User prompt template for contextualization
- `qa_system_prompt` - System prompt for answering questions
- `qa_user_prompt` - User prompt template for QA

**Functions:**
- `get_contextualize_prompt_template()` - Get contextualization prompts
- `get_qa_prompt_template()` - Get QA prompts

### Document Processing Module (`app/services/document_processing/`)

Handles document loading, processing, and storage.

#### Text Splitter (`text_splitter.py`)
Splits text into optimized chunks.

**Functions:**
- `split_text_for_txt(documents)` - Split text into 800-character chunks with 100-char overlap

#### File Loaders (`file_loaders.py`)
Loads and extracts text from various file formats.

**Functions:**
- `extract_text_from_file(file_content, filename, content_type)` - Extract text from PDF/TXT/DOCX
- `validate_file_type(filename, content_type)` - Validate file type is supported
- `get_file_extension_from_content_type(content_type)` - Get extension from MIME type

**Supported Formats:**
- PDF (`.pdf`)
- Text (`.txt`)
- Word Documents (`.docx`)

#### Storage (`storage.py`)
Manages file storage in Supabase.

**Functions:**
- `upload_file_to_supabase(file_content, filename, company_id, doc_id)` - Upload to Supabase
- `get_supabase_storage_client()` - Get Supabase client for storage
- `get_content_type(filename)` - Get MIME type from filename

**Constants:**
- `DOCUMENTS_BUCKET` - Supabase bucket name for documents

## Backward Compatibility

### `langchain_service.py`

This file maintains backward compatibility by re-exporting all RAG functions. Existing code can continue to import from `app.services.langchain_service` without changes.

**Example:**
```python
# Old import (still works)
from app.services.langchain_service import get_company_rag_chain, stream_company_response

# New import (preferred)
from app.services.rag import get_company_rag_chain, stream_company_response
```

### `document_service.py`

This file maintains backward compatibility by re-exporting all document processing functions.

**Example:**
```python
# Old import (still works)
from app.services.document_service import split_text_for_txt, extract_text_from_file

# New import (preferred)
from app.services.document_processing import split_text_for_txt, extract_text_from_file
```

## Usage Examples

### Creating a RAG Chain

```python
from app.services.rag import get_company_rag_chain

# Get RAG chain for a company (creates and caches if not exists)
rag_chain = get_company_rag_chain(
    company_id="company_123",
    llm_model="Groq"  # or "OpenAI"
)
```

### Processing a Document

```python
from app.services.rag import process_company_document

# Process document and add to knowledge base
success = await process_company_document(
    company_id="company_123",
    document_content="Document text here...",
    doc_id="doc_456"  # optional, for status tracking
)
```

### Streaming Responses

```python
from app.services.rag import stream_company_response

# Stream response from RAG chain
async for chunk in stream_company_response(
    company_id="company_123",
    query="What is our return policy?",
    chat_id="chat_789",
    llm_model="Groq"
):
    print(chunk, end="", flush=True)
```

### Extracting Text from Files

```python
from app.services.document_processing import extract_text_from_file

# Extract text from uploaded file
text = await extract_text_from_file(
    file_content=file.read(),
    filename="document.pdf",
    content_type="application/pdf"
)
```

### Uploading Files to Storage

```python
from app.services.document_processing import upload_file_to_supabase

# Upload file to Supabase storage
file_url = await upload_file_to_supabase(
    file_content=file.read(),
    filename="document.pdf",
    company_id="company_123",
    doc_id="doc_456"
)
```

## Cache Management

The RAG system uses intelligent caching to improve performance:

1. **Vector Store Cache** - Caches Pinecone vector store connections per company
2. **RAG Chain Cache** - Caches RAG chains per company and model

**Clear cache when:**
- New documents are uploaded (automatically handled)
- Company data is updated
- Manual refresh is needed

```python
from app.services.rag import clear_company_cache, clear_all_cache

# Clear cache for specific company
clear_company_cache("company_123")

# Clear all caches (use sparingly)
clear_all_cache()
```

## LangSmith Tracing

All chain functions have LangSmith tracing enabled with `@traceable` decorators:

- `get_company_rag_chain`
- `create_conversational_rag_chain`
- `create_contextualization_chain`
- `create_retrieval_chain`
- `create_qa_chain`

This allows monitoring and debugging of RAG operations in the LangSmith dashboard.

## Migration Guide

To migrate existing code to use the new modular structure:

### Before (Old):
```python
from app.services.langchain_service import (
    get_company_rag_chain,
    stream_company_response,
    process_company_document
)
from app.services.document_service import split_text_for_txt
```

### After (New):
```python
from app.services.rag import (
    get_company_rag_chain,
    stream_company_response,
    process_company_document
)
from app.services.document_processing import split_text_for_txt
```

**Note:** The old imports still work due to backward compatibility layers, but new code should use the new imports for clarity.

## Technical Details

### Multi-Tenant Architecture

The system uses Pinecone namespaces for multi-tenant isolation:
- Single base index: `chatelio-multi-tenant`
- Company-specific namespaces: `company_{company_id}`
- Dimension: 1024 (Cohere embed-english-v3.0)
- Metric: cosine similarity

### Chat History Management

- **Contextualization:** Uses ALL available chat history
- **Final Answer:** Only uses LAST 5 MESSAGES
- **Reason:** Reduces token usage while maintaining context understanding

### LLM Models

- **Groq:** llama-3.1-8b-instant (default)
- **OpenAI:** gpt-3.5-turbo (optional)

### Embedding Model

- **Cohere:** embed-english-v3.0
- **Dimension:** 1024
- **API Key:** Required in .env file

## Environment Variables

Required environment variables:

```env
# LLM APIs
GROQ_API_KEY=your-groq-api-key-here
OPENAI_API_KEY=your-openai-api-key-here  # optional

# Embeddings
COHERE_API_KEY=your-cohere-api-key-here

# Vector Database
PINECONE_API_KEY=your-pinecone-api-key-here

# Storage
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# Monitoring
LANGSMITH_API_KEY=your-langsmith-api-key  # optional
LANGSMITH_TRACING_V2=true  # optional
```

## Troubleshooting

### Import Errors

If you see import errors after the refactoring:
1. Ensure `__init__.py` files exist in all module directories
2. Check that backward compatibility layers are in place
3. Verify all imports use correct module paths

### Cache Issues

If responses are stale or incorrect:
1. Clear company cache: `clear_company_cache(company_id)`
2. Check if documents are properly embedded
3. Verify Pinecone namespace contains data

### API Key Errors

If you see API key errors:
1. Verify `.env` file has all required keys
2. Check keys are not placeholder values
3. Ensure keys are valid and have proper permissions

## Best Practices

1. **Use New Imports:** Prefer `app.services.rag` over `app.services.langchain_service`
2. **Cache Management:** Let the system handle cache automatically
3. **Error Handling:** Always wrap RAG operations in try-except blocks
4. **LangSmith:** Keep tracing enabled for production debugging
5. **Testing:** Test with different models and company IDs

## Future Enhancements

Potential improvements to consider:

1. Add more embedding models (OpenAI, HuggingFace)
2. Support more LLM providers (Anthropic, Mistral)
3. Add batch document processing
4. Implement document versioning
5. Add analytics and usage tracking
6. Support more file formats (PPT, Excel, etc.)