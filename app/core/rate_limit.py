# -*- coding: utf-8 -*-
"""
Rate limiting middleware for production deployments.
"""
import time
import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory rate limit store (use Redis for distributed deployments)
_rate_limit_store: dict[str, list[float]] = {}


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key from request (IP or API key)."""
    # Prefer API key over IP for authenticated requests
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key}"

    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/", "/api/admin/health", "/healthz"]:
            return await call_next(request)

        key = get_rate_limit_key(request)
        now = time.time()
        window = settings.RATE_LIMIT_WINDOW
        limit = settings.RATE_LIMIT_REQUESTS

        # Initialize or clean old entries
        if key not in _rate_limit_store:
            _rate_limit_store[key] = []

        # Remove entries outside the window
        _rate_limit_store[key] = [
            ts for ts in _rate_limit_store[key]
            if now - ts < window
        ]

        # Check limit
        if len(_rate_limit_store[key]) >= limit:
            logger.warning(f"Rate limit exceeded for {key}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": window,
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + window)),
                },
            )

        # Record request
        _rate_limit_store[key].append(now)

        response = await call_next(request)

        # Add rate limit headers
        remaining = limit - len(_rate_limit_store[key])
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now + window))

        return response


def reset_rate_limits() -> None:
    """Reset all rate limits (for testing)."""
    _rate_limit_store.clear()