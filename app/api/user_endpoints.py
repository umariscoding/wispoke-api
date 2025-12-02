"""
User management endpoints for the hybrid model (guest sessions + registered users)
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Dict, Any, Optional
from app.models.models import UserRegisterModel, UserLoginModel, GuestSessionModel
from app.auth import create_user_tokens, create_guest_tokens
from app.auth.dependencies import get_current_user, get_current_user_or_guest, UserContext
from app.db.operations.company import create_company, get_company_by_id
from app.db.operations.user import (
    create_user, authenticate_user, get_user_by_id, get_users_by_company_id
)
from app.db.operations.guest import create_guest_session, get_guest_session

router = APIRouter(prefix="/users", tags=["user_management"])

@router.post("/guest/create")
async def create_guest_session_endpoint(
    guest_data: GuestSessionModel,
    request: Request
) -> Dict[str, Any]:
    """
    Create a new guest session for anonymous users.
    
    Args:
        guest_data: Guest session data including company_id
        request: FastAPI request object to extract IP/user agent
        
    Returns:
        Dict containing guest session info and tokens
        
    Raises:
        HTTPException: If company not found or session creation fails
    """
    try:
        # Verify company exists
        company = await get_company_by_id(guest_data.company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Extract IP and user agent from request
        ip_address = guest_data.ip_address or (request.client.host if request.client else "unknown")
        user_agent = guest_data.user_agent or request.headers.get("user-agent", "")
        
        # Create guest session
        session = await create_guest_session(
            company_id=guest_data.company_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Generate tokens
        tokens = create_guest_tokens(
            session_id=session["session_id"],
            company_id=guest_data.company_id
        )
        
        return {
            "message": "Guest session created successfully",
            "session": {
                "session_id": session["session_id"],
                "company_id": session["company_id"],
                "ip_address": session.get("ip_address"),
                "user_agent": session.get("user_agent"),
                "created_at": session.get("created_at"),
                "expires_at": session["expires_at"]
            },
            "tokens": tokens
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create guest session: {str(e)}"
        )

@router.post("/register")
async def register_user(user_data: UserRegisterModel) -> Dict[str, Any]:
    """
    Register a new user for a company.
    
    Args:
        user_data: User registration information
        
    Returns:
        Dict containing user info and authentication tokens
        
    Raises:
        HTTPException: If company not found or registration fails
    """
    try:
        # Verify company exists
        company = await get_company_by_id(user_data.company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Create user account
        user = await create_user(
            company_id=user_data.company_id,
            email=user_data.email,
            password=user_data.password,
            name=user_data.name
        )
        
        # Generate authentication tokens
        tokens = create_user_tokens(
            user_id=user["user_id"],
            company_id=user["company_id"],
            email=user["email"]
        )
        
        return {
            "message": "User registered successfully",
            "user": {
                "user_id": user["user_id"],
                "company_id": user["company_id"],
                "email": user["email"],
                "name": user["name"],
                "is_anonymous": user["is_anonymous"],
                "created_at": user.get("created_at")
            },
            "tokens": tokens
        }
        
    except ValueError as e:
        # Handle duplicate email error
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists in this company"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register user: {str(e)}"
        )

@router.post("/login")
async def login_user(user_data: UserLoginModel) -> Dict[str, Any]:
    """
    Authenticate a user and return tokens.
    
    Args:
        user_data: User login credentials
        
    Returns:
        Dict containing user info and authentication tokens
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Authenticate user
        user = await authenticate_user(
            company_id=user_data.company_id,
            email=user_data.email,
            password=user_data.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Generate authentication tokens
        tokens = create_user_tokens(
            user_id=user["user_id"],
            company_id=user["company_id"],
            email=user["email"]
        )
        
        return {
            "message": "Login successful",
            "user": user,
            "tokens": tokens
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.get("/profile")
async def get_user_profile(current_user: UserContext = Depends(get_current_user_or_guest)) -> Dict[str, Any]:
    """
    Get the current user's profile (works for both guests and registered users).
    
    Args:
        current_user: Current user context
        
    Returns:
        Dict containing user profile information
    """
    try:
        if current_user.is_guest():
            # Get guest session info
            session = await get_guest_session(current_user.user_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Guest session not found or expired"
                )
            
            return {
                "session": {
                    "session_id": session["session_id"],
                    "company_id": session["company_id"],
                    "ip_address": session.get("ip_address"),
                    "user_agent": session.get("user_agent"),
                    "created_at": session.get("created_at"),
                    "expires_at": session["expires_at"]
                },
                "user_type": "guest"
            }
        else:
            # Get registered user info
            user = await get_user_by_id(current_user.user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            return {
                "user": {
                    "user_id": user["user_id"],
                    "company_id": user["company_id"],
                    "email": user["email"],
                    "name": user["name"],
                    "is_anonymous": user["is_anonymous"],
                    "created_at": user.get("created_at")
                },
                "user_type": "user"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )

@router.get("/session/check")
async def check_session_validity(current_user: UserContext = Depends(get_current_user_or_guest)) -> Dict[str, Any]:
    """
    Check if the current session/user is still valid.
    Useful for frontend to verify tokens and session state.
    
    Args:
        current_user: Current user context
        
    Returns:
        Dict containing session validity and user info
    """
    try:
        return {
            "valid": True,
            "user_info": {
                "user_id": current_user.user_id,
                "company_id": current_user.company_id,
                "email": current_user.email,
                "user_type": current_user.user_type
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session check failed: {str(e)}"
        )

@router.get("/company/{company_id}/info")
async def get_company_info(company_id: str, current_user: UserContext = Depends(get_current_user_or_guest)) -> Dict[str, Any]:
    """
    Get company information - users can only access their own company's info.
    
    Args:
        company_id: Company identifier
        current_user: Current authenticated user
        
    Returns:
        Dict containing company information
        
    Raises:
        HTTPException: If user tries to access other company's info
    """
    try:
        # Security check: Users can only access their own company's information
        if current_user.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own company's information"
            )
        
        company = await get_company_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Return company information (user has access to their own company)
        return {
            "company": {
                "company_id": company["company_id"],
                "name": company["name"],
                "status": company["status"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company info: {str(e)}"
        )

@router.get("/company/{company_id}/users")
async def get_company_users(
    company_id: str, 
    current_user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all users for a specific company.
    
    Only company admins can access their own company's user list.
    Regular users and guests cannot access this endpoint.
    
    Args:
        company_id: Company identifier
        current_user: Current authenticated user (must be company)
        
    Returns:
        Dict containing list of users for the company
        
    Raises:
        HTTPException: If user is not authorized or company not found
    """
    try:
        # Security check: Only companies can access user lists
        if not current_user.is_company():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Only company admins can view user lists"
            )
        
        # Security check: Companies can only access their own user lists
        if current_user.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own company's users"
            )
        
        # Verify company exists
        company = await get_company_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Get all users for the company
        users = await get_users_by_company_id(company_id)
        
        return {
            "company_id": company_id,
            "company_name": company["name"],
            "total_users": len(users),
            "users": users
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company users: {str(e)}"
        )

# Health check endpoint
@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for user management service.
    
    Returns:
        Dict containing health status
    """
    return {
        "status": "healthy",
        "service": "user_management"
    } 