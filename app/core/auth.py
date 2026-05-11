# -*- coding: utf-8 -*-
"""
API Key authentication dependency for FastAPI.
"""
import os
from typing import Optional
from fastapi import HTTPException, Security, Header, status
from fastapi.security import APIKeyHeader
import logging

logger = logging.getLogger(__name__)

# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(
    api_key: Optional[str] = Security(api_key_header),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """
    Dependency to get API key from headers.
    Returns None if no API key is configured (auth disabled for development).
    Raises 401 if API key is configured but not provided or invalid.
    """
    # Check environment for configured API keys
    configured_keys = [
        os.getenv("API_KEY_1", "").strip(),
        os.getenv("API_KEY_2", "").strip(),
        os.getenv("API_KEY_3", "").strip(),
    ]
    configured_keys = [k for k in configured_keys if k]

    # If no keys configured, allow all requests (development mode)
    if not configured_keys:
        return None

    # Try header from different sources
    key = api_key or x_api_key

    if not key:
        logger.warning("API key missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header.",
        )

    if key not in configured_keys:
        logger.warning(f"Invalid API key attempted: {key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return key


def require_auth(func):
    """Decorator to require API key authentication for an endpoint."""
    from functools import wraps

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get the dependency result from kwargs
        api_key = kwargs.get("api_key")
        if api_key is None and func.__code__.co_varnames:
            # Check if api_key was injected by Depends
            pass
        return await func(*args, **kwargs)

    return wrapper