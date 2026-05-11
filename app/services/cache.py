# -*- coding: utf-8 -*-
"""
Redis caching service for production deployments.
"""
import json
import logging
from typing import Optional, Any
from functools import wraps
import hashlib

import redis
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Redis client singleton
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client, returns None if Redis is unavailable."""
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            _redis_client.ping()
            logger.info("Redis connected successfully")
        except redis.ConnectionError as e:
            logger.warning(f"Redis unavailable: {e}. Running without cache.")
            _redis_client = None
        except Exception as e:
            logger.error(f"Redis error: {e}")
            _redis_client = None

    return _redis_client


def cache_key(*args, **kwargs) -> str:
    """Generate a cache key from function arguments."""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return "bhakti:" + hashlib.md5(key_data.encode()).hexdigest()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Decorator to cache function results in Redis.

    Args:
        ttl: Cache TTL in seconds (uses settings.CACHE_TTL by default)
        key_prefix: Prefix for the cache key
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            if redis_client is None:
                return await func(*args, **kwargs)

            cache_ttl = ttl or settings.CACHE_TTL
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            try:
                cached_result = redis_client.get(key)
                if cached_result:
                    logger.debug(f"Cache hit: {key}")
                    return json.loads(cached_result)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

            result = await func(*args, **kwargs)

            try:
                redis_client.setex(key, cache_ttl, json.dumps(result, default=str))
                logger.debug(f"Cache set: {key}")
            except Exception as e:
                logger.warning(f"Cache write error: {e}")

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            if redis_client is None:
                return func(*args, **kwargs)

            cache_ttl = ttl or settings.CACHE_TTL
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"

            try:
                cached_result = redis_client.get(key)
                if cached_result:
                    logger.debug(f"Cache hit: {key}")
                    return json.loads(cached_result)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")

            result = func(*args, **kwargs)

            try:
                redis_client.setex(key, cache_ttl, json.dumps(result, default=str))
                logger.debug(f"Cache set: {key}")
            except Exception as e:
                logger.warning(f"Cache write error: {e}")

            return result

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def invalidate_cache(pattern: str) -> int:
    """Invalidate cache keys matching pattern. Returns count of deleted keys."""
    redis_client = get_redis_client()
    if redis_client is None:
        return 0

    try:
        keys = list(redis_client.scan_iter(f"*{pattern}*"))
        if keys:
            count = redis_client.delete(*keys)
            logger.info(f"Invalidated {count} cache keys matching '{pattern}'")
            return count
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
    return 0


def close_redis() -> None:
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client:
        try:
            _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")
        finally:
            _redis_client = None