# -*- coding: utf-8 -*-
"""
Bhakti Marg AI - FastAPI Application
Production-ready with structured logging, auth, and graceful shutdown.
"""
import logging
import signal
import sys
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

from app.core.config import get_settings
from app.core.logging import setup_logging, RequestIDMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.routes.api import router as api_router
from app.database.connection import engine, Base
from app.services.vector_store import init_index
from app.core.shutdown import shutdown_handler, register_cleanup
from app.services.cache import close_redis

settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


def _auto_fetch_missing_transcripts():
    """Background thread to auto-fetch missing transcripts on startup."""
    try:
        from app.services.auto_transcript_fetcher import fetch_missing_transcripts
        logger.info("Starting automatic transcript fetching...")
        fetch_missing_transcripts()
        logger.info("Automatic transcript fetching complete")
    except Exception as e:
        logger.error(f"Auto transcript fetch error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting Bhakti Marg AI...", extra={"app_version": settings.APP_VERSION})

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")

    # Initialize FAISS index
    init_index()
    logger.info("FAISS index initialized")

    # Register cleanup for Redis
    register_cleanup(close_redis)

    # Auto-fetch missing transcripts in background (only in production)
    if not settings.DEBUG:
        logger.info("Starting background transcript fetcher...")
        thread = threading.Thread(target=_auto_fetch_missing_transcripts, daemon=True)
        thread.start()

    yield

    # Shutdown
    logger.info("Shutting down gracefully...")
    shutdown_handler()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# CORS - use allowed origins from config
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static and template dirs exist during mount
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("templates"):
    os.makedirs("templates")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(api_router, prefix="/api")


@app.get("/")
async def serve_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_config=None,  # Use our custom logging
    )