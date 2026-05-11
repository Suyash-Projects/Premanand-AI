# -*- coding: utf-8 -*-
"""
Structured logging configuration with request ID tracking.
"""
import logging
import sys
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variable for request ID (thread-safe)
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request-id")


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add JSON handler for stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Set third-party loggers to WARNING to reduce noise
    for logger_name in ["uvicorn", "fastapi", "sqlalchemy", "httpx"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_var.get()


def set_request_id(req_id: str | None = None) -> str:
    """Set request ID in context. Generates one if not provided."""
    rid = req_id or str(uuid.uuid4())
    request_id_var.set(rid)
    return rid


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request ID into every request."""

    async def dispatch(self, request: Request, call_next):
        # Check for existing request ID in header or generate new one
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(req_id)

        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class LogContext:
    """Context manager for adding extra fields to log entries."""

    def __init__(self, **kwargs: Any):
        self.fields = kwargs
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            record.extra_fields = self.fields
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args):
        logging.setLogRecordFactory(self.old_factory)