"""
Tests for JWT token creation, verification, and decoding.
"""

import time
from datetime import timedelta

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
    decode_token,
    refresh_access_token,
    create_company_tokens,
    create_user_tokens,
    create_guest_tokens,
    get_current_user_info,
    is_company_token,
    is_user_token,
    is_guest_token,
)


class TestAccessToken:
    def test_create_and_verify(self):
        token = create_access_token({"sub": "user-1", "user_type": "company"})
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["type"] == "access"

    def test_expired_token_returns_none(self):
        token = create_access_token(
            {"sub": "user-1"}, expires_delta=timedelta(seconds=-1)
        )
        assert verify_token(token) is None

    def test_invalid_token_returns_none(self):
        assert verify_token("not.a.valid.token") is None
        assert verify_token("") is None
        assert verify_token("abc123") is None


class TestRefreshToken:
    def test_create_and_verify(self):
        token = create_refresh_token({"sub": "user-1", "user_type": "company"})
        payload = verify_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"

    def test_refresh_access_token(self):
        refresh = create_refresh_token({
            "sub": "company-1", "email": "a@b.com", "user_type": "company"
        })
        new_access = refresh_access_token(refresh)
        assert new_access is not None
        payload = decode_token(new_access)
        assert payload["sub"] == "company-1"
        assert payload["type"] == "access"

    def test_refresh_with_access_token_fails(self):
        access = create_access_token({"sub": "user-1", "user_type": "company"})
        assert refresh_access_token(access) is None

    def test_refresh_with_invalid_token_fails(self):
        assert refresh_access_token("invalid") is None


class TestCompanyTokens:
    def test_creates_both_tokens(self):
        tokens = create_company_tokens("cid-1", "admin@co.com")
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"

    def test_user_info_extraction(self):
        tokens = create_company_tokens("cid-1", "admin@co.com")
        info = get_current_user_info(tokens["access_token"])
        assert info["company_id"] == "cid-1"
        assert info["email"] == "admin@co.com"
        assert info["user_type"] == "company"

    def test_is_company_token(self):
        tokens = create_company_tokens("cid-1", "admin@co.com")
        assert is_company_token(tokens["access_token"]) is True
        assert is_user_token(tokens["access_token"]) is False
        assert is_guest_token(tokens["access_token"]) is False


class TestUserTokens:
    def test_creates_both_tokens(self):
        tokens = create_user_tokens("uid-1", "cid-1", "u@co.com")
        assert "access_token" in tokens

    def test_user_info_extraction(self):
        tokens = create_user_tokens("uid-1", "cid-1", "u@co.com")
        info = get_current_user_info(tokens["access_token"])
        assert info["user_id"] == "uid-1"
        assert info["company_id"] == "cid-1"
        assert info["user_type"] == "user"

    def test_is_user_token(self):
        tokens = create_user_tokens("uid-1", "cid-1")
        assert is_user_token(tokens["access_token"]) is True
        assert is_company_token(tokens["access_token"]) is False


class TestGuestTokens:
    def test_creates_both_tokens(self):
        tokens = create_guest_tokens("sess-1", "cid-1")
        assert "access_token" in tokens

    def test_user_info_extraction(self):
        tokens = create_guest_tokens("sess-1", "cid-1")
        info = get_current_user_info(tokens["access_token"])
        assert info["user_id"] == "sess-1"
        assert info["company_id"] == "cid-1"
        assert info["user_type"] == "guest"

    def test_is_guest_token(self):
        tokens = create_guest_tokens("sess-1", "cid-1")
        assert is_guest_token(tokens["access_token"]) is True


class TestEdgeCases:
    def test_unknown_user_type_returns_none(self):
        token = create_access_token({"sub": "x", "user_type": "alien"})
        assert get_current_user_info(token) is None

    def test_missing_user_type_returns_none(self):
        token = create_access_token({"sub": "x"})
        assert get_current_user_info(token) is None
