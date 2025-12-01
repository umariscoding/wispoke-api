from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os

class Settings(BaseSettings):
    """
    Application settings using Pydantic BaseSettings.
    Automatically loads from environment variables and .env file.
    """
    
    # API Keys
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    cohere_api_key: Optional[str] = os.getenv("COHERE_API_KEY")
    groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    pinecone_api_key: Optional[str] = os.getenv("PINECONE_API_KEY")
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_key: Optional[str] = os.getenv("SUPABASE_KEY")

    # JWT Configuration
    jwt_secret_key: str = "your-secret-key-change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # AI Configuration
    embedding_model: str = "embed-english-v3.0"  # Cohere embedding model
    
    # Database
    database_url: str = "postgresql://username:password@localhost:5432/chatelio_db"
    
    # Domain Configuration
    base_domain: str = "mysite.com"
    chatbot_protocol: str = "https"  # http for dev, https for prod
    use_subdomain_routing: bool = True
    
    # Development Settings
    debug: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables

@lru_cache()
def get_settings():
    """
    Create a cached instance of settings.
    This ensures settings are loaded only once.
    """
    return Settings()

# Export settings instance for easy access
settings = get_settings()

# Backward compatibility - export individual variables
EMBEDDING_MODEL = settings.embedding_model
DATABASE_URL = settings.database_url
BASE_DOMAIN = settings.base_domain
CHATBOT_PROTOCOL = settings.chatbot_protocol
USE_SUBDOMAIN_ROUTING = settings.use_subdomain_routing

def get_chatbot_url(slug: str) -> str:
    """
    Generate the public chatbot URL for a given company slug.
    
    Args:
        slug: Company slug
        
    Returns:
        str: Full chatbot URL
        
    Examples:
        - Development: http://kfcchatbot.localhost:8000
        - Production: https://kfcchatbot.mysite.com
    """
    if USE_SUBDOMAIN_ROUTING:
        return f"{CHATBOT_PROTOCOL}://{slug}.{BASE_DOMAIN}"
    else:
        # Fallback to path-based routing
        return f"{CHATBOT_PROTOCOL}://{BASE_DOMAIN}/public/chatbot/{slug}"