"""
Application middleware — subdomain detection, request logging with correlation IDs.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("chatevo.middleware")


class SubdomainMiddleware(BaseHTTPMiddleware):
    """
    Detect and extract subdomain information from the Host header.
    Sets `request.state.subdomain` and `request.state.is_subdomain_request`.
    """

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        subdomain = None

        if "." in host:
            parts = host.split(".")
            if len(parts) >= 3:
                subdomain = parts[0].split(":")[0]
            elif len(parts) == 2:
                domain_part = parts[1].split(":")[0]
                if domain_part == "localhost" or "." not in parts[1]:
                    subdomain = parts[0].split(":")[0]

        is_subdomain_request = (
            subdomain is not None
            and subdomain not in ("www", "api", "admin", "dashboard")
            and len(subdomain) >= 3
        )

        request.state.subdomain = subdomain
        request.state.is_subdomain_request = is_subdomain_request
        request.state.original_host = host

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every request with a correlation ID, method, path, status, and duration.
    The correlation ID is also set on the response as X-Request-ID.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id

        subdomain = getattr(request.state, "subdomain", None)
        sub_tag = f" [sub={subdomain}]" if subdomain else ""

        logger.info(
            "%s %s %s %d %.0fms%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            sub_tag,
        )
        return response
