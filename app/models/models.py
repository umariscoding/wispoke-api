from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from typing import Optional
import time
import uuid

Base = declarative_base()

# Generate unique IDs
def generate_id():
    return str(uuid.uuid4())

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, unique=True, nullable=False, default=generate_id)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=True)  # URL-friendly company identifier
    plan = Column(String, default='free')  # free, basic, pro, enterprise
    status = Column(String, default='active')  # active, suspended, deleted
    is_published = Column(Boolean, default=False)  # whether chatbot is published
    published_at = Column(DateTime, nullable=True)  # when chatbot was published
    chatbot_title = Column(String, nullable=True)  # custom chatbot title
    chatbot_description = Column(String, nullable=True)  # custom chatbot description
    api_keys = Column(JSON, default=dict)  # store encrypted API keys
    settings = Column(JSON, default=dict)  # chatbot customization settings
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    users = relationship("CompanyUser", back_populates="company")
    chats = relationship("Chat", back_populates="company")
    guest_sessions = relationship("GuestSession", back_populates="company")
    knowledge_bases = relationship("KnowledgeBase", back_populates="company")

class CompanyUser(Base):
    __tablename__ = "company_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, unique=True, nullable=False, default=generate_id)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)  # Hashed password for registered users
    name = Column(String, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    user_metadata = Column(JSON, default=dict)  # store additional user data
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="users")
    chats = relationship("Chat", back_populates="user")

class GuestSession(Base):
    __tablename__ = "guest_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False, default=generate_id)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="guest_sessions")
    chats = relationship("Chat", back_populates="guest_session")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String, unique=True, nullable=False, default=generate_id)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default='processing')  # processing, ready, failed
    file_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String, unique=True, nullable=False, default=generate_id)
    kb_id = Column(String, ForeignKey("knowledge_bases.kb_id"), nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    embeddings_status = Column(String, default='pending')  # pending, processing, completed, failed
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, unique=True, nullable=False, default=generate_id)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    user_id = Column(String, ForeignKey("company_users.user_id"), nullable=True)
    session_id = Column(String, ForeignKey("guest_sessions.session_id"), nullable=True)
    title = Column(String, nullable=False)
    is_guest = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="chats")
    user = relationship("CompanyUser", back_populates="chats")
    guest_session = relationship("GuestSession", back_populates="chats")
    messages = relationship("Message", back_populates="chat")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String, unique=True, nullable=False, default=generate_id)
    chat_id = Column(String, ForeignKey("chats.chat_id"), nullable=False)
    company_id = Column(String, ForeignKey("companies.company_id"), nullable=False)
    role = Column(String, nullable=False)  # human, ai, system
    content = Column(Text, nullable=False)
    timestamp = Column(Integer, default=lambda: int(time.time()))
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")

# Pydantic models for API requests
class QueryModel(BaseModel):
    question: str
    model: str
    chat_id: str
    chat_name: str

class CompanyRegisterModel(BaseModel):
    name: str
    email: str
    password: str

class CompanyLoginModel(BaseModel):
    email: str
    password: str

class UserRegisterModel(BaseModel):
    email: str
    password: str
    name: str
    company_id: str

class UserLoginModel(BaseModel):
    email: str
    password: str
    company_id: str

class GuestSessionModel(BaseModel):
    company_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class CompanySlugModel(BaseModel):
    slug: str

class PublishChatbotModel(BaseModel):
    is_published: bool

class ChatbotInfoModel(BaseModel):
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None

class BatchUpdateSettingsModel(BaseModel):
    slug: Optional[str] = None
    chatbot_title: Optional[str] = None
    chatbot_description: Optional[str] = None
    is_published: Optional[bool] = None


class PublicChatMessage(BaseModel):
    message: str
    chat_id: Optional[str] = None
    model: str = "Llama-instant"  # Default to fast Llama model

class EmbedSettingsModel(BaseModel):
    theme: Optional[str] = "dark"  # dark, light
    position: Optional[str] = "right"  # left, right
    primaryColor: Optional[str] = "#6366f1"
    welcomeText: Optional[str] = "Hi there! How can we help you today?"
    subtitleText: Optional[str] = "We typically reply instantly"