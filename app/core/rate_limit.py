"""
In-memory sliding-window rate limiter with automatic eviction.

For multi-worker / multi-instance production deployments, replace this with
a Redis-backed implementation (e.g., using `redis` + a Lua sliding-window script).
This module is designed to be a drop-in replacement target for that migration.
"""

import time
import logging
from collections import defaultdict
from typing import Dict, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("chatevo.rate_limit")

DEFAULT_MAX_REQUESTS = 60
DEFAULT_WINDOW_SECONDS = 60
_EVICTION_INTERVAL = 300  # purge stale IPs every 5 minutes


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware — sliding-window rate limit by client IP.

    Args:
        app: ASGI application.
        max_requests: Maximum requests per window.
        window_seconds: Window size in seconds.
        exempt_paths: Paths that skip rate limiting.
    """

    def __init__(
        self,
        app,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        exempt_paths: set[str] | None = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths or {
            "/", "/health",
            "/auth/health", "/chat/health",
            "/users/health", "/public/health",
        }
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._last_eviction = time.time()

    # ------------------------------------------------------------------
    # Eviction — prevent unbounded memory growth
    # ------------------------------------------------------------------

    def _maybe_evict(self, now: float) -> None:
        if now - self._last_eviction < _EVICTION_INTERVAL:
            return
        self._last_eviction = now
        cutoff = now - self.window_seconds
        stale_keys = [ip for ip, ts in self._requests.items() if not ts or ts[-1] < cutoff]
        for key in stale_keys:
            del self._requests[key]

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self.exempt_paths:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old timestamps for this IP and append current
        timestamps = self._requests[client_ip]
        self._requests[client_ip] = [t for t in timestamps if t > cutoff]
        self._requests[client_ip].append(now)

        self._maybe_evict(now)

        if len(self._requests[client_ip]) > self.max_requests:
            retry_after = int(self.window_seconds - (now - self._requests[client_ip][0]))
            retry_after = max(1, retry_after)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
