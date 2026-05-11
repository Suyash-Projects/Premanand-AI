# -*- coding: utf-8 -*-
"""
Graceful shutdown handler for production deployments.
"""
import logging
import threading
from typing import Callable
from functools import wraps

logger = logging.getLogger(__name__)

_shutdown_event = threading.Event()
_cleanup_callbacks: list[Callable] = []


def register_cleanup(callback: Callable) -> None:
    """Register a callback to be called during shutdown."""
    _cleanup_callbacks.append(callback)


def shutdown_handler() -> None:
    """Execute all registered cleanup callbacks."""
    _num_callbacks = len(_cleanup_callbacks)
    logger.info(f"Running {_num_callbacks} cleanup callbacks...")
    for callback in _cleanup_callbacks:
        try:
            callback()
            logger.debug(f"Cleanup completed: {callback.__name__}")
        except Exception as e:
            logger.error(f"Cleanup error in {callback.__name__}: {e}")
    _cleanup_callbacks.clear()


def is_shutting_down() -> bool:
    """Check if shutdown is in progress."""
    return _shutdown_event.is_set()


def require_not_shutting_down(func):
    """Decorator to skip operations during shutdown."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if is_shutting_down():
            logger.warning(f"Skipping {func.__name__} - shutdown in progress")
            return None
        return func(*args, **kwargs)
    return wrapper