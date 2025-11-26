# Chatelio - Multi-Tenant Chatbot-as-a-Service Platform

A FastAPI-based multi-tenant chatbot platform that provides Chatbot-as-a-Service with Retrieval-Augmented Generation (RAG) capabilities. Companies can create their own chatbots, upload knowledge bases, and deploy them with custom subdomains.

## Features

- **Multi-Tenant Architecture**: Complete company isolation with separate knowledge bases
- **RAG-powered Q&A**: Companies can upload documents and create intelligent chatbots
- **Subdomain Routing**: Each company gets their own chatbot URL (e.g., `companyname.chatelio.com`)
- **Guest & Registered Users**: Support for both anonymous guests and registered users
- **Document Management**: Upload and manage knowledge base documents
- **Chat History**: Persistent chat history with complete user isolation
- **Authentication**: JWT-based authentication with role-based access control
- **Streaming Responses**: Real-time streaming of AI responses
- **RESTful API**: Full REST API for integration with frontend applications

## Prerequisites

- Python 3.8+
- Google AI API key
- Pinecone account (for vector database)
- OpenAI API key (for embeddings)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/umariscoding/chat-backend.git
   cd chat-backend
   ```

2. **Install dependencies**
   ```bash
   conda create -n chatelio python=3.11
   conda activate  chatelio
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the `app/` directory with the following variables:
   ```env
   # Google AI Configuration
   GOOGLE_API_KEY=your_google_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   
   # OpenAI Configuration (for embeddings)
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Pinecone Configuration
   PINECONE_API_KEY=your_pinecone_api_key_here
   
   # Optional Configuration
   MODEL_NAME=gemini-1.5-pro-latest
   EMBEDDING_MODEL=models/embedding-001
   CHROMA_DB_PATH=chroma_db
   DATABASE_URL=sqlite:///chat_history.db
   ```

## Running the Application

### Using Uvicorn (Recommended)
```bash
uvicorn app.main:app --reload --port 8081
```

### Using Python directly
```bash
python -m app.main
```

The application will be available at: http://localhost:8081

## API Endpoints

### Chat Management
- `GET /get-all-chats` - Get all chat sessions
- `GET /get-all-messages/{chat_id}` - Get messages for a specific chat
- `POST /save-chat/{chat_id}/{chat_name}` - Save a new chat
- `POST /edit-chat-title/{chat_id}/{new_title}` - Update chat title
- `POST /delete-chat/{chat_id}` - Delete a specific chat
- `POST /delete-all-chats/` - Delete all chats

### Q&A Processing
- `POST /process-txt/` - Process a text query using RAG about Umar Azhar
- `POST /update-data/` - Update and process Umar Azhar's information in the vector database

## Sample Questions

You can ask questions like:
- "What is Umar Azhar's educational background?"
- "What programming languages does Umar know?"
- "Tell me about Umar's work experience"
- "What projects has Umar worked on?"
- "What are Umar's technical skills?"

## Project Structure

```
chat-backend/
├── app/
│   ├── api/
│   │   └── endpoints.py          # API route definitions
│   ├── core/
│   │   └── config.py             # Configuration settings
│   ├── db/
│   │   └── database.py           # Database operations
│   ├── jobs/
│   │   └── scheduler.py          # Background job scheduler
│   ├── models/
│   │   └── models.py             # SQLAlchemy models
│   ├── services/
│   │   ├── document_service.py   # Document processing
│   │   ├── fetchdata_service.py  # Static data about Umar Azhar
│   │   ├── langchain_service.py  # LangChain integration
│   │   └── prompts.py            # AI prompts
│   └── main.py                   # FastAPI application entry point
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## Security Notes

- Never commit API keys or tokens to version control
- Use environment variables for all sensitive configuration
- The `.env` file is automatically ignored by git
- Regularly rotate your API keys and tokens

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 