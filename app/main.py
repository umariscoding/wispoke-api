import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from app.features.auth.router import router as auth_router
from app.features.users.router import router as user_router
from app.features.chat.router import router as chat_router
from app.features.documents.router import router as documents_router
from app.features.public.router import router as public_router
from app.features.analytics.router import router as analytics_router
from app.features.legacy.router import router as legacy_router

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

# Include feature routers
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(public_router)
app.include_router(analytics_router)
app.include_router(legacy_router)

# Serve embed widget script
@app.get("/embed.js")
async def serve_embed_script():
    """Serve the embed widget JavaScript file."""
    embed_path = os.path.join(STATIC_DIR, "embed.js")
    return FileResponse(
        embed_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*"
        }
    )

# Serve full-page preview for a company's chatbot widget
@app.get("/preview/{company_slug}")
async def serve_widget_preview(company_slug: str, request: Request):
    """Serve a full-page preview of the embed widget for a company."""
    base_url = str(request.base_url).rstrip("/")
    # Only upgrade to HTTPS in production (not localhost)
    if "localhost" not in base_url and "127.0.0.1" not in base_url:
        base_url = base_url.replace("http://", "https://", 1)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Widget Preview — {company_slug}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f0f5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .preview-banner {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: #18181b;
            color: #a1a1aa;
            text-align: center;
            padding: 8px 16px;
            font-size: 13px;
            z-index: 1000000;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}
        .preview-banner strong {{
            color: #e4e4e7;
        }}
        .preview-dot {{
            width: 6px;
            height: 6px;
            background: #22c55e;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        .sample-content {{
            max-width: 800px;
            padding: 80px 24px 24px;
            width: 100%;
        }}
        .sample-content h1 {{
            font-size: 28px;
            color: #18181b;
            margin-bottom: 8px;
        }}
        .sample-content p {{
            color: #71717a;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 16px;
        }}
        .sample-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .sample-card h3 {{
            font-size: 16px;
            color: #18181b;
            margin-bottom: 8px;
        }}
        .sample-card p {{
            font-size: 14px;
            color: #71717a;
        }}
    </style>
</head>
<body>
    <div class="preview-banner">
        <span class="preview-dot"></span>
        <span><strong>Preview Mode</strong> — This is how the widget appears on your website</span>
    </div>
    <div class="sample-content">
        <h1>Your Website</h1>
        <p>This is a preview of how the ChatEvo widget will look on your website. The chat widget is loaded in the bottom corner — click it to interact.</p>
        <div class="sample-card">
            <h3>Sample Section</h3>
            <p>This placeholder content simulates your website. The chat widget will float above your content, ready for visitors to use.</p>
        </div>
        <div class="sample-card">
            <h3>Another Section</h3>
            <p>Your visitors can browse your site normally while the chat widget is available for questions and support.</p>
        </div>
    </div>

    <!-- ChatEvo Widget -->
    <script
        src="{base_url}/embed.js"
        data-company-slug="{company_slug}"
        data-api-url="{base_url}"
        async
    ></script>
</body>
</html>"""
    return HTMLResponse(content=html)

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
