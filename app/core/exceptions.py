"""
Application-level exceptions.

Services raise these; the global exception handler in main.py
converts them to HTTP responses. Routers never need try/except.
"""


class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class AuthorizationError(AppException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status_code=403)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400)


class ConflictError(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)


class RateLimitError(AppException):
    def __init__(self, message: str = "Too many requests", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, status_code=429)


class InternalError(AppException):
    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, status_code=500)
