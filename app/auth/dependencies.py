"""
FastAPI authentication dependencies and middleware for JWT validation
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from app.auth.jwt import get_current_user_info, is_company_token, is_user_token, is_guest_token
from app.db.operations.company import get_company_by_id
from app.db.operations.user import get_user_by_id
from app.db.operations.guest import get_guest_session

# Security scheme
security = HTTPBearer()

class UserContext:
    """User context object containing authentication information"""
    def __init__(self, user_id: str, company_id: str, user_type: str, email: Optional[str] = None):
        self.user_id = user_id
        self.company_id = company_id
        self.user_type = user_type
        self.email = email
        
    def is_company(self) -> bool:
        return self.user_type == "company"
        
    def is_user(self) -> bool:
        return self.user_type == "user"
        
    def is_guest(self) -> bool:
        return self.user_type == "guest"

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserContext:
    """
    Extract and validate user information from JWT token.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        UserContext: User context object
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    # Decode token
    user_info = get_current_user_info(token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_type = user_info.get("user_type")
    email = user_info.get("email")
    
    if not user_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Handle different token types
    if user_type == "company":
        # For company tokens, the ID is in company_id field
        company_id = user_info.get("company_id")
        user_id = company_id  # Use company_id as user_id for compatibility
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # For user/guest tokens, the ID is in user_id field
        user_id = user_info.get("user_id")
        company_id = user_info.get("company_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Validate user exists in database
    if user_type == "company":
        company = await get_company_by_id(user_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Company not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        company_id = company["company_id"]
    elif user_type == "user":
        user = await get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        company_id = user["company_id"]
    elif user_type == "guest":
        session = await get_guest_session(user_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Guest session not found or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        company_id = session["company_id"]
    
    # Ensure company_id is not None
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid company context",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return UserContext(user_id, company_id, user_type, email)

async def get_current_company(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """
    Ensure the current user is a company.
    
    Args:
        current_user: Current user context
        
    Returns:
        UserContext: Company user context
        
    Raises:
        HTTPException: If user is not a company
    """
    if not current_user.is_company():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company access required"
        )
    
    return current_user

async def get_current_user_or_guest(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """
    Allow both registered users and guests.
    
    Args:
        current_user: Current user context
        
    Returns:
        UserContext: User or guest context
        
    Raises:
        HTTPException: If user is a company (not allowed)
    """
    if current_user.is_company():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User or guest access required"
        )
    
    return current_user

async def get_company_context(current_user: UserContext = Depends(get_current_user)) -> str:
    """
    Extract company_id from any type of authenticated user.
    
    Args:
        current_user: Current user context
        
    Returns:
        str: Company ID
    """
    return current_user.company_id

def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[UserContext]:
    """
    Optional authentication - doesn't raise exception if no token provided.
    
    Args:
        credentials: Optional HTTP Bearer token credentials
        
    Returns:
        Optional[UserContext]: User context if token provided and valid, None otherwise
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        user_info = get_current_user_info(token)
        if not user_info:
            return None
        
        user_id = user_info.get("user_id")
        company_id = user_info.get("company_id")
        user_type = user_info.get("user_type")
        email = user_info.get("email")
        
        if not user_id or not user_type:
            return None
        
        # For company tokens, company_id is the same as user_id
        if user_type == "company":
            company_id = user_id
        
        # Ensure company_id is not None
        if not company_id:
            return None
        
        return UserContext(user_id, company_id, user_type, email)
    except Exception:
        return None

# Common dependency combinations
async def require_company_auth(current_user: UserContext = Depends(get_current_company)) -> UserContext:
    """Require company authentication."""
    return current_user

async def require_user_auth(current_user: UserContext = Depends(get_current_user_or_guest)) -> UserContext:
    """Require user or guest authentication."""
    return current_user

async def require_any_auth(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """Require any type of authentication."""
    return current_user

# Utility functions for route protection
def company_required(func):
    """Decorator to require company authentication."""
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or not current_user.is_company():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company access required"
            )
        return await func(*args, **kwargs)
    return wrapper

def user_required(func):
    """Decorator to require user or guest authentication."""
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or current_user.is_company():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User or guest access required"
            )
        return await func(*args, **kwargs)
    return wrapper 