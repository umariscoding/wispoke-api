"""
Application-level exceptions.

Services raise these; routers catch them and convert to HTTP responses.
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


class InternalError(AppException):
    def __init__(self, message: str = "Internal server error"):
        super().__init__(message, status_code=500)
