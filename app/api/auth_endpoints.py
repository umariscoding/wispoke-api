"""
Authentication endpoints for company management
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Any
from app.models.models import CompanyRegisterModel, CompanyLoginModel, CompanySlugModel, PublishChatbotModel, ChatbotInfoModel, BatchUpdateSettingsModel, EmbedSettingsModel
from app.auth import (
    create_company_tokens, verify_password, get_password_hash,
    refresh_access_token, get_current_user_info
)
from app.auth.dependencies import get_current_company, UserContext
from app.db.operations.company import (
    create_company, authenticate_company, get_company_by_id,
    update_company_slug, publish_chatbot, update_chatbot_info, get_company_by_slug,
    batch_update_settings, get_embed_settings, update_embed_settings
)
from app.db.operations.user import get_users_by_company_id
from app.core.config import get_chatbot_url

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

class RefreshTokenModel(BaseModel):
    refresh_token: str

@router.post("/company/register")
async def register_company(company_data: CompanyRegisterModel) -> Dict[str, Any]:
    """
    Register a new company account.
    
    Args:
        company_data: Company registration information
        
    Returns:
        Dict containing company info and authentication tokens
        
    Raises:
        HTTPException: If company already exists or registration fails
    """
    try:
        # Hash password before storing
        hashed_password = get_password_hash(company_data.password)

        # Create company account
        company = await create_company(
            name=company_data.name,
            email=company_data.email,
            password=hashed_password
        )
        
        # Generate authentication tokens
        tokens = create_company_tokens(
            company_id=company["company_id"],
            email=company["email"]
        )
        
        return {
            "message": "Company registered successfully",
            "company": company,
            "tokens": tokens
        }
        
    except ValueError as e:
        # Company already exists
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Other registration errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/company/login")
async def login_company(login_data: CompanyLoginModel) -> Dict[str, Any]:
    """
    Authenticate a company and return tokens.
    
    Args:
        login_data: Company login credentials
        
    Returns:
        Dict containing company info and authentication tokens
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Authenticate company
        company = await authenticate_company(
            email=login_data.email,
            password=login_data.password
        )
        
        if not company:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Generate authentication tokens
        tokens = create_company_tokens(
            company_id=company["company_id"],
            email=company["email"]
        )
        
        return {
            "message": "Login successful",
            "company": company,
            "tokens": tokens
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.get("/company/profile")
async def get_company_profile(current_company: UserContext = Depends(get_current_company)) -> Dict[str, Any]:
    """
    Get the authenticated company's profile information.
    
    Args:
        current_company: Authenticated company context
        
    Returns:
        Dict containing company profile information
    """
    try:
        company = await get_company_by_id(current_company.company_id)
        
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        return {
            "company": company
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )

@router.post("/refresh")
async def refresh_tokens(refresh_data: RefreshTokenModel) -> Dict[str, Any]:
    """
    Refresh access token using refresh token.
    
    Args:
        refresh_data: Request body containing refresh token
        
    Returns:
        Dict containing new access token
        
    Raises:
        HTTPException: If refresh token is invalid
    """
    try:
        refresh_token = refresh_data.refresh_token
        
        # Generate new access token
        new_access_token = refresh_access_token(refresh_token)
        
        if not new_access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # JWT signature verification failures should return 401, not 500
        error_message = str(e)
        if "signature" in error_message.lower() or "invalid" in error_message.lower() or "decode" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Token refresh failed: {error_message}"
            )

@router.get("/verify")
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Verify and decode a JWT token.
    
    Args:
        credentials: HTTP Bearer token
        
    Returns:
        Dict containing user information from token
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        token = credentials.credentials
        
        # Get user info from token
        user_info = get_current_user_info(token)
        
        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        return {
            "valid": True,
            "user_info": user_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # JWT signature verification failures should return 401, not 500
        error_message = str(e)
        if "signature" in error_message.lower() or "invalid" in error_message.lower() or "decode" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Token verification failed: {error_message}"
            )

@router.post("/company/logout")
async def logout_company(current_company: UserContext = Depends(get_current_company)) -> Dict[str, Any]:
    """
    Logout a company (client-side token invalidation).
    
    Args:
        current_company: Authenticated company context
        
    Returns:
        Dict containing logout confirmation
    """
    # Note: JWT tokens are stateless, so logout is primarily client-side
    # In a production system, you might want to implement token blacklisting
    
    return {
        "message": "Logout successful",
        "company_id": current_company.company_id
    }

@router.put("/company/slug")
async def update_company_slug_endpoint(
    slug_data: CompanySlugModel,
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Update company slug for public chatbot URL.
    
    Args:
        slug_data: New slug information
        current_company: Current company context
        
    Returns:
        dict: Success message and new slug
        
    Raises:
        HTTPException: If slug already exists or update fails
    """
    try:
        # Validate slug format (URL-friendly)
        import re
        if not re.match(r'^[a-zA-Z0-9-_]+$', slug_data.slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug must contain only letters, numbers, hyphens, and underscores"
            )
        
        # Check length
        if len(slug_data.slug) < 3 or len(slug_data.slug) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug must be between 3 and 50 characters long"
            )
        
        # Update slug
        success = await update_company_slug(
            company_id=current_company.company_id,
            slug=slug_data.slug
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update slug"
            )
        
        return {
            "message": "Company slug updated successfully",
            "slug": slug_data.slug,
            "public_url": get_chatbot_url(slug_data.slug)
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update slug: {str(e)}"
        )

@router.post("/company/publish-chatbot")
async def publish_chatbot_endpoint(
    publish_data: PublishChatbotModel,
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Publish or unpublish company chatbot.
    
    Args:
        publish_data: Publishing configuration
        current_company: Current company context
        
    Returns:
        dict: Success message and publishing status
        
    Raises:
        HTTPException: If company has no slug or publish fails
    """
    try:
        # Get current company info to check if slug exists
        company = await get_company_by_id(current_company.company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Check if company has a slug (required for publishing)
        if publish_data.is_published and not company.get("slug"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company must have a slug before publishing. Please set a slug first."
            )
        
        # Publish/unpublish chatbot
        success = await publish_chatbot(
            company_id=current_company.company_id,
            is_published=publish_data.is_published
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update publishing status"
            )
        
        response_data = {
            "message": f"Chatbot {'published' if publish_data.is_published else 'unpublished'} successfully",
            "is_published": publish_data.is_published
        }
        
        if publish_data.is_published and company.get("slug"):
            response_data["public_url"] = get_chatbot_url(company["slug"])
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish chatbot: {str(e)}"
        )

@router.put("/company/chatbot-info")
async def update_chatbot_info_endpoint(
    chatbot_data: ChatbotInfoModel,
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Update company chatbot title and description.
    
    Args:
        chatbot_data: Chatbot information to update
        current_company: Current company context
        
    Returns:
        dict: Success message and updated info
        
    Raises:
        HTTPException: If update fails
    """
    try:
        # Validate that at least one field is provided
        if chatbot_data.chatbot_title is None and chatbot_data.chatbot_description is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field (chatbot_title or chatbot_description) must be provided"
            )
        
        # Update chatbot info
        success = await update_chatbot_info(
            company_id=current_company.company_id,
            chatbot_title=chatbot_data.chatbot_title,
            chatbot_description=chatbot_data.chatbot_description
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update chatbot information"
            )
        
        response_data = {
            "message": "Chatbot information updated successfully"
        }
        
        # Include the updated values in response
        if chatbot_data.chatbot_title is not None:
            response_data["chatbot_title"] = chatbot_data.chatbot_title
        if chatbot_data.chatbot_description is not None:
            response_data["chatbot_description"] = chatbot_data.chatbot_description
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update chatbot info: {str(e)}"
        )

@router.get("/company/chatbot-status")
async def get_chatbot_status(
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Get current chatbot publishing status.
    
    Args:
        current_company: Current company context
        
    Returns:
        dict: Current chatbot status
        
    Raises:
        HTTPException: If company not found
    """
    try:
        company = await get_company_by_id(current_company.company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        return {
            "company_id": company["company_id"],
            "slug": company.get("slug"),
            "is_published": company.get("is_published", False),
            "published_at": company.get("published_at"),
            "chatbot_title": company.get("chatbot_title"),
            "chatbot_description": company.get("chatbot_description"),
            "public_url": get_chatbot_url(company["slug"]) if company.get("slug") and company.get("is_published") else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chatbot status: {str(e)}"
        )

@router.get("/company/users")
async def get_company_users(current_company: UserContext = Depends(get_current_company)) -> Dict[str, Any]:
    """
    Get all users for the current company (company admin only).
    
    Args:
        current_company: Current authenticated company admin
        
    Returns:
        Dict containing list of company users
        
    Raises:
        HTTPException: If company not found
    """
    try:
        # Verify company exists
        company = await get_company_by_id(current_company.company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )
        
        # Get all users for the company
        users = await get_users_by_company_id(current_company.company_id)
        
        return {
            "company_id": current_company.company_id,
            "company_name": company["name"],
            "users": users,
            "total_users": len(users)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get company users: {str(e)}"
        )

@router.put("/company/settings")
async def batch_update_settings_endpoint(
    settings_data: BatchUpdateSettingsModel,
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Batch update company settings (slug, chatbot info, publish status).

    Args:
        settings_data: Settings to update
        current_company: Current company context

    Returns:
        dict: Success message and updated company data

    Raises:
        HTTPException: If validation fails or update fails
    """
    try:
        # Validate at least one field is provided
        if (settings_data.slug is None and
            settings_data.chatbot_title is None and
            settings_data.chatbot_description is None and
            settings_data.is_published is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field must be provided"
            )

        # Validate slug format if provided
        if settings_data.slug is not None:
            import re
            if not re.match(r'^[a-z0-9-]+$', settings_data.slug):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Slug must contain only lowercase letters, numbers, and hyphens"
                )
            if len(settings_data.slug) < 3 or len(settings_data.slug) > 50:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Slug must be between 3 and 50 characters long"
                )

        # Check if trying to publish without slug
        if settings_data.is_published:
            company = await get_company_by_id(current_company.company_id)
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Company not found"
                )
            # If no slug provided in update and company doesn't have one
            if settings_data.slug is None and not company.get("slug"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Company must have a slug before publishing"
                )

        # Perform batch update
        updated_company = await batch_update_settings(
            company_id=current_company.company_id,
            slug=settings_data.slug,
            chatbot_title=settings_data.chatbot_title,
            chatbot_description=settings_data.chatbot_description,
            is_published=settings_data.is_published
        )

        if not updated_company:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update settings"
            )

        return {
            "message": "Settings updated successfully",
            "company": updated_company
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )

@router.get("/company/embed-settings")
async def get_embed_settings_endpoint(
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Get embed widget settings for the company.

    Args:
        current_company: Current company context

    Returns:
        dict: Embed settings
    """
    try:
        settings = await get_embed_settings(current_company.company_id)
        return {
            "settings": settings
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get embed settings: {str(e)}"
        )


@router.put("/company/embed-settings")
async def update_embed_settings_endpoint(
    settings_data: EmbedSettingsModel,
    current_company: UserContext = Depends(get_current_company)
) -> Dict[str, Any]:
    """
    Update embed widget settings for the company.

    Args:
        settings_data: Embed settings to update
        current_company: Current company context

    Returns:
        dict: Updated embed settings
    """
    try:
        updated_settings = await update_embed_settings(
            company_id=current_company.company_id,
            theme=settings_data.theme,
            position=settings_data.position,
            primary_color=settings_data.primaryColor,
            welcome_text=settings_data.welcomeText,
            subtitle_text=settings_data.subtitleText
        )

        if updated_settings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )

        return {
            "message": "Embed settings updated successfully",
            "settings": updated_settings
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update embed settings: {str(e)}"
        )


# Health check endpoint
@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for authentication service.

    Returns:
        Dict containing health status
    """
    return {
        "status": "healthy",
        "service": "authentication"
    } 