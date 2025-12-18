import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.endpoints import router as api_router
from app.api.auth_endpoints import router as auth_router
from app.api.user_endpoints import router as user_router
from app.api.chat_endpoints import router as chat_router
from app.api.public_endpoints import router as public_router
from app.api.analytics_endpoints import router as analytics_router

app = FastAPI()

# Get the directory where this file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enable CORS with subdomain support
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # For development - will be more restrictive in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add subdomain detection middleware
@app.middleware("http")
async def subdomain_middleware(request: Request, call_next):
    """
    Middleware to detect and extract subdomain information from requests.
    Sets subdomain info in request.state for use by endpoints.
    
    Examples:
    - kfcchatbot.mysite.com → subdomain="kfcchatbot", is_subdomain_request=True
    - www.mysite.com → subdomain="www", is_subdomain_request=False  
    - mysite.com → subdomain=None, is_subdomain_request=False
    - localhost:8000 → subdomain=None, is_subdomain_request=False
    - imrankhan.localhost:3001 → subdomain="imrankhan", is_subdomain_request=True
    """
    host = request.headers.get("host", "").lower()
    subdomain = None
    
    # Extract subdomain
    if "." in host:
        parts = host.split(".")
        
        # Handle different domain formats
        if len(parts) >= 3:  # Production: subdomain.domain.tld
            subdomain = parts[0].split(":")[0]  # Remove port if present
        elif len(parts) == 2:  # Development: subdomain.localhost:port or subdomain.domain
            # Check if this is a localhost development scenario
            domain_part = parts[1].split(":")[0]  # Remove port from domain part
            if domain_part == "localhost" or not "." in parts[1]:
                subdomain = parts[0].split(":")[0]  # Remove port if present
    
    # Determine if this is a chatbot subdomain request
    is_subdomain_request = (
        subdomain is not None and 
        subdomain not in ["www", "api", "admin", "dashboard"] and
        len(subdomain) >= 3  # Minimum slug length
    )
    
    # Store in request state
    request.state.subdomain = subdomain
    request.state.is_subdomain_request = is_subdomain_request
    request.state.original_host = host
    
    # Log subdomain detection for debugging
    logger.info(f"Host: {host} → Subdomain: {subdomain}, Is subdomain request: {is_subdomain_request}")
    if is_subdomain_request:
        logger.info(f"✅ Detected chatbot subdomain: {subdomain} from host: {host}")
    else:
        logger.info(f"ℹ️  No valid subdomain detected from host: {host}")
    
    response = await call_next(request)
    return response

# Add middleware to log API hits
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log incoming API requests.

    Args:
        request (Request): The incoming request object.
        call_next: A function to call the next middleware or endpoint.

    Returns:
        Response: The response object after processing the request.
    """
    subdomain_info = f" [subdomain: {getattr(request.state, 'subdomain', 'none')}]" if hasattr(request.state, 'subdomain') else ""
    logger.info(f"API hit: {request.method} {request.url.path}{subdomain_info}")
    response = await call_next(request)
    return response

# Include the routers
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(public_router)
app.include_router(analytics_router)
app.include_router(api_router)

# Serve embed widget script
@app.get("/embed.js")
async def serve_embed_script():
    """Serve the embed widget JavaScript file."""
    embed_path = os.path.join(STATIC_DIR, "embed.js")
    return FileResponse(
        embed_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"
        }
    )

# Mount static files directory
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Add root health check
@app.get("/")
async def root():
    """Root endpoint for health checking and basic info."""
    return {
        "message": "Chatelio Multi-Tenant Chatbot API",
        "status": "healthy",
        "version": "1.0.0"
    }

# Add this line to make the app importable
main = app

# Run the app with uvicorn when this script is executed directly
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting the application")
    uvicorn.run("app.main:app", port=8081)