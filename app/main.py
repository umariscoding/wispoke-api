"""
Wispoke API — application entry point.

Creates the FastAPI app, registers middleware, exception handlers, and routers.
"""

import logging
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.core.exceptions import AppException, RateLimitError
from app.core.middleware import RequestLoggingMiddleware
from app.core.rate_limit import RateLimitMiddleware

from app.features.auth.router import router as auth_router
from app.features.users.router import router as user_router
from app.features.chat.router import router as chat_router
from app.features.documents.router import router as documents_router
from app.features.public.router import router as public_router
from app.features.analytics.router import router as analytics_router
from app.features.billing.router import router as billing_router
from app.features.availability.router import router as availability_router
from app.features.appointments.router import router as appointments_router
from app.features.voice_agent.router import router as voice_agent_router

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Wispoke API",
    description="Multi-tenant chatbot platform with RAG-powered responses",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

_jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wispoke")

# ---------------------------------------------------------------------------
# Middleware (order matters — outermost first)
# ---------------------------------------------------------------------------

# CORS — restrict in production, allow-all only behind a flag
ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(RequestLoggingMiddleware)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException):
    headers = {}
    if isinstance(exc, RateLimitError):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(public_router)
app.include_router(analytics_router)
app.include_router(billing_router)
app.include_router(availability_router)
app.include_router(appointments_router)
app.include_router(voice_agent_router)

# ---------------------------------------------------------------------------
# Static / widget endpoints
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


@app.get("/embed.js")
async def serve_embed_script():
    embed_path = os.path.join(STATIC_DIR, "embed.js")
    return FileResponse(
        embed_path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
    )


@app.get("/preview/{company_slug}")
async def serve_widget_preview(company_slug: str, request: Request):
    # Validate slug to prevent XSS
    if not _SLUG_RE.match(company_slug):
        return JSONResponse(status_code=400, content={"detail": "Invalid company slug"})

    base_url = str(request.base_url).rstrip("/")
    if "localhost" not in base_url and "127.0.0.1" not in base_url:
        base_url = base_url.replace("http://", "https://", 1)

    template = _jinja_env.get_template("widget_preview.html")
    html = template.render(company_slug=company_slug, base_url=base_url)
    return HTMLResponse(content=html)


# Mount static files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "message": "Wispoke Multi-Tenant Chatbot API",
        "status": "healthy",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

main = app

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Wispoke API")
    uvicorn.run("app.main:app", port=8081, reload=True)
