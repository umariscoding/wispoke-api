"""
Shared test fixtures for the ChatEvo API test suite.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

# Set test environment variables BEFORE importing app modules
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-supabase-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long-for-validation")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key")
os.environ.setdefault("COHERE_API_KEY", "test-cohere-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


@pytest.fixture(autouse=True)
def _mock_supabase(monkeypatch):
    """Mock the Supabase client for all tests so no real DB calls are made."""
    mock_client = MagicMock()
    monkeypatch.setattr("app.core.database._db", mock_client)
    monkeypatch.setattr("app.core.database.db", mock_client)
    return mock_client


@pytest.fixture
def app():
    """Create the FastAPI test app."""
    from app.main import app as _app
    return _app


@pytest.fixture
def client(app):
    """Create a TestClient for the app."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def sample_company():
    """Sample company data for tests."""
    return {
        "company_id": "test-company-id-1234",
        "name": "Test Company",
        "slug": "test-company",
        "email": "admin@test.com",
        "password_hash": "$2b$12$dummy",
        "is_published": True,
        "chatbot_title": "Test Bot",
        "chatbot_description": "A test chatbot",
        "default_model": "Llama-large",
        "system_prompt": "",
        "tone": "professional",
        "status": "active",
        "plan": "free",
        "settings": {},
    }


@pytest.fixture
def sample_user():
    """Sample user data for tests."""
    return {
        "user_id": "test-user-id-1234",
        "company_id": "test-company-id-1234",
        "email": "user@test.com",
        "name": "Test User",
        "is_anonymous": False,
        "created_at": "2025-01-01T00:00:00Z",
    }


@pytest.fixture
def auth_headers():
    """Generate valid auth headers for testing."""
    from app.core.security import create_access_token
    token = create_access_token({
        "sub": "test-company-id-1234",
        "email": "admin@test.com",
        "user_type": "company",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_auth_headers():
    """Generate valid user auth headers for testing."""
    from app.core.security import create_access_token
    token = create_access_token({
        "sub": "test-user-id-1234",
        "company_id": "test-company-id-1234",
        "email": "user@test.com",
        "user_type": "user",
    })
    return {"Authorization": f"Bearer {token}"}
