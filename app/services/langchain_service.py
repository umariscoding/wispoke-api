import time
from langchain_cohere import CohereEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_groq import ChatGroq
from pinecone import Pinecone, ServerlessSpec
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from typing import AsyncGenerator, List, Dict, Optional
from app.core.config import settings, EMBEDDING_MODEL
from app.services.prompts import contextualize_q_system_prompt, qa_system_prompt
from app.services.document_service import split_text_for_txt
from app.db.database import update_document_embeddings_status, load_session_history

# Only raise errors when the services are actually used, not at import time
def check_openai_key():
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is not set in the environment variables.")

def check_cohere_key():
    if not settings.cohere_api_key:
        raise ValueError("Cohere API key is not set in the environment variables.")

def check_groq_key():
    if not settings.groq_api_key:
        raise ValueError("Groq API key is not set in the environment variables.")

def check_pinecone_key():
    if not settings.pinecone_api_key:
        raise ValueError("Pinecone API key is not set in the environment variables.")

def get_openai_api_key():
    """Get the current OpenAI API key from settings."""
    return settings.openai_api_key

def get_cohere_api_key():
    """Get the current Cohere API key from settings."""
    return settings.cohere_api_key

def get_groq_api_key():
    """Get the current Groq API key from settings."""
    return settings.groq_api_key

def get_pinecone_api_key():
    """Get the current Pinecone API key from settings."""
    return settings.pinecone_api_key

# Initialize Pinecone (lazy initialization)
pc = None

def get_pinecone_client():
    global pc
    if pc is None:
        check_pinecone_key()
        pc = Pinecone(api_key=get_pinecone_api_key())
    return pc

# Base index name for all companies
BASE_INDEX_NAME = "chatelio-multi-tenant"

# Performance optimization: Cache frequently used objects
_company_vector_stores: Dict[str, PineconeVectorStore] = {}
_company_rag_chains: Dict[str, Dict[str, RunnableWithMessageHistory]] = {}

def get_company_index_name(company_id: str) -> str:
    """
    Generate a company-specific index name.
    For now, we use the same base index but with namespaces.
    """
    return BASE_INDEX_NAME

def get_company_namespace(company_id: str) -> str:
    """
    Generate a company-specific namespace within the index.
    """
    return f"company_{company_id}"

def ensure_base_index_exists():
    """
    Ensure the base multi-tenant index exists with optimal configuration.
    """
    try:
        existing_indexes = [index_info["name"] for index_info in get_pinecone_client().list_indexes()]
        
        if BASE_INDEX_NAME not in existing_indexes:
            get_pinecone_client().create_index(
                name=BASE_INDEX_NAME,
                dimension=1024,  # Cohere embed-english-v3.0 dimension
                metric="cosine",  # Best for text similarity
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                ),
            )
            # Wait for index to be ready with timeout
            max_wait = 300  # 5 minutes timeout
            waited = 0
            while not get_pinecone_client().describe_index(BASE_INDEX_NAME).status["ready"]:
                if waited >= max_wait:
                    raise TimeoutError(f"Index creation timed out after {max_wait} seconds")
                time.sleep(5)
                waited += 5
                
    except Exception as e:
        raise e

def create_company_vector_store(company_id: str, doc_chunks: List[str]) -> PineconeVectorStore:
    """
    Create a company-specific vector store with the provided document chunks.
    
    Args:
        company_id (str): Company ID
        doc_chunks (List[str]): List of text chunks to embed
        
    Returns:
        PineconeVectorStore: Company-specific vector store
    """
    global _company_vector_stores, _company_rag_chains
    
    # Ensure base index exists
    ensure_base_index_exists()
    
    # Get company namespace
    namespace = get_company_namespace(company_id)

    # Create embeddings with Cohere
    check_cohere_key()
    embedding_function = CohereEmbeddings(
        model=EMBEDDING_MODEL,
        cohere_api_key=get_cohere_api_key()
    )

    # Create vector store with company-specific namespace using best practices
    try:
        # Use optimized configuration for document creation
        vector_store = PineconeVectorStore.from_texts(
            texts=doc_chunks,
            embedding=embedding_function,
            index_name=BASE_INDEX_NAME,
            namespace=namespace,
            text_key="text",  # Explicit text key for metadata
            metadatas=[{"source": f"company_{company_id}", "chunk_id": i} for i in range(len(doc_chunks))]
        )
        
    except Exception as vs_error:
        raise vs_error
    
    # Cache the vector store
    _company_vector_stores[company_id] = vector_store
    
    # Clear RAG chains cache for this company
    if company_id in _company_rag_chains:
        _company_rag_chains[company_id].clear()
    
    return vector_store

def get_company_vector_store(company_id: str) -> PineconeVectorStore:
    """
    Get or create a company-specific vector store.
    
    Args:
        company_id (str): Company ID
        
    Returns:
        PineconeVectorStore: Company-specific vector store
    """
    global _company_vector_stores
    
    # Check if we have a cached vector store
    if company_id in _company_vector_stores:
        return _company_vector_stores[company_id]
    
    # Ensure base index exists
    ensure_base_index_exists()
    
    # Get company namespace
    namespace = get_company_namespace(company_id)

    # Create embeddings with Cohere
    check_cohere_key()
    embedding_function = CohereEmbeddings(
        model=EMBEDDING_MODEL,
        cohere_api_key=get_cohere_api_key()
    )

    # Create vector store connection with company-specific namespace
    # Use explicit index reference for consistent connections
    pinecone_index = get_pinecone_client().Index(BASE_INDEX_NAME)
    
    vector_store = PineconeVectorStore(
        index=pinecone_index,
        embedding=embedding_function,
        namespace=namespace
    )
    
    # Cache the vector store
    _company_vector_stores[company_id] = vector_store
    
    return vector_store

def setup_company_knowledge_base(company_id: str, doc_chunks: List[str]):
    """
    Set up knowledge base for a company. For now, all companies get the same data.
    
    Args:
        company_id (str): Company ID
        doc_chunks (List[str]): Document chunks to store
    """
    result = create_company_vector_store(company_id, doc_chunks)
    return result

async def process_company_document(company_id: str, document_content: str, doc_id: Optional[str] = None) -> bool:
    """
    Process a document for a company's knowledge base.

    Args:
        company_id (str): Company ID
        document_content (str): Document content to process
        doc_id (str, optional): Document ID for tracking

    Returns:
        bool: True if processing was successful
    """
    try:
        # Split document into chunks
        doc_chunks = split_text_for_txt(document_content)

        # Get or create company vector store
        vector_store = get_company_vector_store(company_id)

        # Add document chunks to vector store with metadata
        metadatas = [
            {
                "source": f"document_{doc_id}" if doc_id else "uploaded_document",
                "chunk_id": i,
                "company_id": company_id
            }
            for i in range(len(doc_chunks))
        ]

        vector_store.add_texts(texts=doc_chunks, metadatas=metadatas)

        # Clear RAG chain cache for this company to force refresh
        clear_company_cache(company_id)

        # Update document status if doc_id is provided
        if doc_id:
            try:
                await update_document_embeddings_status(doc_id, 'completed')
            except Exception:
                pass

        return True

    except Exception as e:
        # Update document status to failed if doc_id is provided
        if doc_id:
            try:
                await update_document_embeddings_status(doc_id, 'failed')
            except Exception:
                pass

        return False

def clear_company_knowledge_base(company_id: str):
    """
    Clear all knowledge base content for a company.
    
    Args:
        company_id (str): Company ID
    """
    try:
        # Get company namespace
        namespace = get_company_namespace(company_id)
        
        # Delete all vectors in the namespace
        index = get_pinecone_client().Index(BASE_INDEX_NAME)
        index.delete(delete_all=True, namespace=namespace)
        
        # Clear caches
        clear_company_cache(company_id)
        
        return True
        
    except Exception as e:
        return False

def get_company_rag_chain(company_id: str, llm_model: str = "Groq") -> RunnableWithMessageHistory:
    """
    Get or create a company-specific RAG chain.
    
    Args:
        company_id (str): Company ID
        llm_model (str): LLM model to use
        
    Returns:
        RunnableWithMessageHistory: Company-specific RAG chain
    """
    global _company_rag_chains
    
    # Initialize company cache if not exists
    if company_id not in _company_rag_chains:
        _company_rag_chains[company_id] = {}
    
    # Check if we have a cached RAG chain for this company and model
    if llm_model in _company_rag_chains[company_id]:
        return _company_rag_chains[company_id][llm_model]
    
    # Create fresh vector store for reliable connections
    ensure_base_index_exists()
    namespace = get_company_namespace(company_id)
    check_cohere_key()
    cohere_api_key = get_cohere_api_key()
    embedding_function = CohereEmbeddings(model=EMBEDDING_MODEL, cohere_api_key=cohere_api_key)
    pinecone_index = get_pinecone_client().Index(BASE_INDEX_NAME)
    
    # Fix the vector store wrapper issue by ensuring proper initialization
    vector_store = PineconeVectorStore(
        index=pinecone_index,
        embedding=embedding_function,
        namespace=namespace
        # Remove text_key parameter as it may cause issues
    )
    
    # Create custom retriever for reliable document retrieval
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.documents import Document
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from typing import List, Any
    from pydantic import Field

    class DirectPineconeRetriever(BaseRetriever):
        """Custom retriever that uses direct Pinecone queries for reliable document retrieval."""

        pinecone_index: Any = Field(description="Pinecone index object")
        embedding_function: Any = Field(description="Embedding function")
        namespace: str = Field(description="Pinecone namespace")

        class Config:
            arbitrary_types_allowed = True

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun
        ) -> List[Document]:
            """Retrieve documents relevant to the query."""
            try:
                # Generate embedding for the query
                query_embedding = self.embedding_function.embed_query(query)

                # Query Pinecone directly
                results = self.pinecone_index.query(
                    vector=query_embedding,
                    top_k=8,  # Increased from 4 to retrieve more relevant chunks
                    namespace=self.namespace,
                    include_metadata=True
                )

                # Convert results to LangChain documents
                documents = []
                for match in results.matches:
                    if hasattr(match, 'metadata') and match.metadata:
                        text = match.metadata.get('text', '')
                        if text.strip():  # Only add non-empty documents
                            doc = Document(
                                page_content=text,
                                metadata={
                                    **match.metadata,
                                    'score': match.score if hasattr(match, 'score') else 0.0
                                }
                            )
                            documents.append(doc)

                return documents

            except Exception as e:
                return []

    # Use custom retriever for reliable document retrieval
    retriever = DirectPineconeRetriever(
        pinecone_index=pinecone_index,
        embedding_function=embedding_function,
        namespace=namespace
    )

    # Create LLM (using Groq with deepseek-r1-distill-llama-70b)
    if llm_model == "Groq":
        check_groq_key()
        groq_api_key = get_groq_api_key()
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=groq_api_key,
            temperature=0.7
        )
    elif llm_model == "OpenAI":
        check_openai_key()
        openai_api_key = get_openai_api_key()
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(openai_api_key=openai_api_key)
    else:
        raise ValueError(f"Model {llm_model} not available. Only Groq and OpenAI are supported.")
    
    # Create prompts
    contextualize_q_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    # Create optimized RAG chain using latest patterns
    try:
        # Create history-aware retriever
        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, contextualize_q_prompt
        )
        
        # Create question-answer chain
        question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
        
        # Create retrieval chain
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)
        
        # Create session history function with error handling
        def get_session_history(chat_id: str) -> BaseChatMessageHistory:
            try:
                return load_session_history(company_id, chat_id)
            except Exception:
                # Return empty history as fallback
                from langchain_core.chat_history import InMemoryChatMessageHistory
                return InMemoryChatMessageHistory()
        
        # Create conversational RAG chain with proper configuration
        conversational_rag_chain = RunnableWithMessageHistory(
            rag_chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )
        
    except Exception as chain_error:
        raise chain_error
    
    # Cache the chain
    _company_rag_chains[company_id][llm_model] = conversational_rag_chain
    
    return conversational_rag_chain

async def stream_company_response(company_id: str, query: str, chat_id: str, llm_model: str = "Groq") -> AsyncGenerator[str, None]:
    """
    Stream response from company-specific RAG chain.

    Args:
        company_id (str): Company ID
        query (str): User query
        chat_id (str): Chat ID
        llm_model (str): LLM model to use (default: Groq)

    Yields:
        str: Response chunks
    """
    try:
        # Check API keys based on the model
        if llm_model == "Groq":
            groq_key = get_groq_api_key()
            if not groq_key or groq_key == "your-groq-api-key-here":
                yield "Error: Groq API key not configured. Please create a .env file in the project root and set GROQ_API_KEY=your-actual-groq-key. You can get an API key from https://console.groq.com/"
                return
        elif llm_model == "OpenAI":
            openai_key = get_openai_api_key()
            if not openai_key or openai_key == "your-openai-api-key-here":
                yield "Error: OpenAI API key not configured. Please create a .env file in the project root and set OPENAI_API_KEY=your-actual-openai-key. You can get an API key from https://platform.openai.com/api-keys"
                return

        # Check if Pinecone API key is available
        pinecone_key = get_pinecone_api_key()

        if not pinecone_key or pinecone_key == "your-pinecone-api-key-here":
            yield "Error: Pinecone API key not configured. Please create a .env file in the project root and set PINECONE_API_KEY=your-actual-pinecone-key. You can get an API key from https://pinecone.io/"
            return

        # Get company-specific RAG chain with comprehensive error handling
        try:
            rag_chain = get_company_rag_chain(company_id, llm_model)
        except Exception as chain_error:
            error_msg = str(chain_error)

            # Provide specific error messages based on error type
            if "unsupported operand" in error_msg.lower():
                yield "Error: Internal retriever compatibility issue. Please try again or contact support."
            elif "pinecone" in error_msg.lower():
                yield f"Error: Knowledge base connection failed. Please ensure documents are uploaded."
            elif "groq" in error_msg.lower() or "openai" in error_msg.lower() or "api" in error_msg.lower():
                yield "Error: AI service connection failed. Please check API configuration."
            else:
                yield f"Error: Failed to initialize chat system. Details: {error_msg}"
            return
        
        # Stream response with timeout handling
        try:
            resp = rag_chain.stream(
                {"input": query},
                config={"configurable": {"session_id": chat_id}},
            )
            
            response_started = False
            
            for chunk in resp:
                if 'answer' in chunk:
                    response_started = True
                    chunk_content = chunk['answer']
                    if chunk_content:  # Only yield non-empty chunks
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
            yield "Error: Invalid or missing OpenAI API key. Please check your API key configuration."
        elif "pinecone" in error_msg.lower():
            yield "Error: Pinecone connection failed. Please check your Pinecone API key configuration."
        else:
            yield f"Error: {error_msg}"

# Legacy compatibility functions (updated to use company context)
def create_embeddings_and_store_text(doc_chunks: List[str], company_id: str = "default") -> PineconeVectorStore:
    """
    Legacy function updated for company context.
    """
    return create_company_vector_store(company_id, doc_chunks)

def get_pinecone_vectorstore(company_id: str = "default") -> PineconeVectorStore:
    """
    Legacy function updated for company context.
    """
    return get_company_vector_store(company_id)

def get_rag_chain(llm_model: str = "OpenAI", company_id: str = "default") -> RunnableWithMessageHistory:
    """
    Legacy function updated for company context.
    """
    return get_company_rag_chain(company_id, llm_model)

def query_pinecone(db: PineconeVectorStore, llm_model: str = "OpenAI", chat_id: str = 'abc123', company_id: str = "default"):
    """
    Legacy function updated for company context.
    """
    return get_company_rag_chain(company_id, llm_model)

async def stream_response(query: str, conversational_rag_chain, chat_id: str = 'abc123', company_id: str = "default") -> AsyncGenerator[str, None]:
    """
    Legacy function - now redirects to company-specific streaming.
    """
    async for chunk in stream_company_response(company_id, query, chat_id):
        yield chunk

# Initialize default company knowledge base for backward compatibility
def initialize_default_knowledge_base(doc_chunks: List[str]):
    """
    Initialize the default knowledge base for backward compatibility.
    """
    create_company_vector_store("default", doc_chunks)

# Cache management functions
def clear_company_cache(company_id: str):
    """Clear cache for a specific company."""
    global _company_vector_stores, _company_rag_chains
    
    if company_id in _company_vector_stores:
        del _company_vector_stores[company_id]
    
    if company_id in _company_rag_chains:
        del _company_rag_chains[company_id]

def clear_all_cache():
    """Clear all cached data."""
    global _company_vector_stores, _company_rag_chains
    
    _company_vector_stores.clear()
    _company_rag_chains.clear()

# For backward compatibility
def clear_cache():
    """Legacy function for clearing cache."""
    clear_all_cache()

def force_refresh_all_rag_chains():
    """Legacy function for refreshing RAG chains."""
    clear_all_cache()
