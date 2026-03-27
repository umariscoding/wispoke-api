"""
Tests for request schema validation.
"""

import pytest
from pydantic import ValidationError

from app.features.auth.schemas import (
    CompanyRegisterRequest,
    CompanyLoginRequest,
    CompanySlugRequest,
    BatchUpdateSettingsRequest,
    EmbedSettingsRequest,
)
from app.features.chat.schemas import ChatMessageRequest
from app.features.users.schemas import UserRegisterRequest


class TestCompanyRegister:
    def test_valid(self):
        req = CompanyRegisterRequest(name="Acme", email="a@b.com", password="12345678")
        assert req.name == "Acme"

    def test_short_name_rejected(self):
        with pytest.raises(ValidationError):
            CompanyRegisterRequest(name="A", email="a@b.com", password="12345678")

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            CompanyRegisterRequest(name="Acme", email="a@b.com", password="short")

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            CompanyRegisterRequest(name="Acme", email="not-an-email", password="12345678")


class TestCompanySlug:
    def test_valid_slug(self):
        req = CompanySlugRequest(slug="my-company-123")
        assert req.slug == "my-company-123"

    def test_invalid_chars_rejected(self):
        with pytest.raises(ValidationError):
            CompanySlugRequest(slug="my company!")

    def test_too_short(self):
        with pytest.raises(ValidationError):
            CompanySlugRequest(slug="ab")


class TestChatMessage:
    def test_valid(self):
        req = ChatMessageRequest(message="Hello!")
        assert req.message == "Hello!"
        assert req.model == "Llama-large"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatMessageRequest(message="")


class TestUserRegister:
    def test_valid(self):
        req = UserRegisterRequest(
            email="u@co.com", password="secure1234", name="Jo", company_id="cid"
        )
        assert req.email == "u@co.com"

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            UserRegisterRequest(
                email="u@co.com", password="short", name="Jo", company_id="cid"
            )


class TestBatchUpdateSettings:
    def test_slug_pattern(self):
        req = BatchUpdateSettingsRequest(slug="my-company")
        assert req.slug == "my-company"

    def test_uppercase_slug_rejected(self):
        with pytest.raises(ValidationError):
            BatchUpdateSettingsRequest(slug="My-Company")


class TestEmbedSettings:
    def test_defaults(self):
        req = EmbedSettingsRequest()
        assert req.theme == "dark"
        assert req.position == "right"
        assert req.autoOpenDelay == 0

    def test_negative_delay_rejected(self):
        with pytest.raises(ValidationError):
            EmbedSettingsRequest(autoOpenDelay=-1)
