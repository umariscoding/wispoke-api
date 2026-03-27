"""
Tests for custom exception hierarchy.
"""

from app.core.exceptions import (
    AppException,
    NotFoundError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    ConflictError,
    RateLimitError,
    InternalError,
)


class TestExceptions:
    def test_base_exception(self):
        exc = AppException("something broke", 418)
        assert exc.message == "something broke"
        assert exc.status_code == 418

    def test_not_found(self):
        exc = NotFoundError()
        assert exc.status_code == 404

    def test_authentication(self):
        exc = AuthenticationError("bad token")
        assert exc.status_code == 401
        assert exc.message == "bad token"

    def test_authorization(self):
        assert AuthorizationError().status_code == 403

    def test_validation(self):
        assert ValidationError().status_code == 400

    def test_conflict(self):
        assert ConflictError().status_code == 409

    def test_rate_limit(self):
        exc = RateLimitError(retry_after=30)
        assert exc.status_code == 429
        assert exc.retry_after == 30

    def test_internal(self):
        assert InternalError().status_code == 500
