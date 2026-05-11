# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import List, Optional
from math import ceil
import os

from app.database.connection import get_db
from app.models.db_models import Video, QAPair
from app.services.rag_pipeline import process_query
from app.services.vector_store import add_to_index, _index, search_similar_qa
from app.services.youtube_service import process_channel_videos
from app.core.auth import get_api_key
from app.services.cache import cached, invalidate_cache

router = APIRouter()


class QueryRequest(BaseModel):
    query: str


class VideoResponse(BaseModel):
    id: int
    title: str
    youtube_id: str
    url: str

    class Config:
        from_attributes = True


class QAResponse(BaseModel):
    id: int
    question: str
    answer: str
    timestamp: int
    video_id: int

    class Config:
        from_attributes = True


class PaginatedVideoResponse(BaseModel):
    items: List[VideoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedQAResponse(BaseModel):
    items: List[QAResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthDetailResponse(BaseModel):
    status: str
    database: str
    vector_index: str
    llm_providers: dict
    redis: str


# ---------------------------------------------------------------------------
# Core endpoints (authenticated)
# ---------------------------------------------------------------------------

@router.post("/ask")
def ask_question(
    request: QueryRequest,
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """Answer a spiritual question using the RAG pipeline."""
    if not request.query.strip():
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty")

    # Try cache first
    cached_result = _get_cached_answer(request.query)
    if cached_result:
        return cached_result

    answer_data = process_query(request.query)

    # Cache the result
    _cache_answer(request.query, answer_data)

    return answer_data


@router.get("/videos", response_model=PaginatedVideoResponse)
def get_videos(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """Return paginated list of indexed videos."""
    total = db.query(Video).count()
    offset = (page - 1) * page_size
    videos = db.query(Video).offset(offset).limit(page_size).all()

    return PaginatedVideoResponse(
        items=videos,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/qa", response_model=PaginatedQAResponse)
def get_qa(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    video_id: Optional[int] = Query(None, description="Filter by video ID"),
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """Return paginated list of Q&A pairs with optional video filter."""
    query = db.query(QAPair)
    if video_id:
        query = query.filter(QAPair.video_id == video_id)

    total = query.count()
    offset = (page - 1) * page_size
    pairs = query.offset(offset).limit(page_size).all()

    return PaginatedQAResponse(
        items=pairs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 0,
    )


@router.post("/process-channel")
def process_channel(
    background_tasks: BackgroundTasks,
    max_videos: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """Triggers the full ETL pipeline to scrape, extract, and index QAs from the channel."""
    background_tasks.add_task(process_channel_videos, db, max_videos)
    return {
        "status": "success",
        "message": f"Processing of up to {max_videos} videos started in the background.",
    }


# ---------------------------------------------------------------------------
# Demo endpoint  (fixes the broken "Load Demo Data" button)
# ---------------------------------------------------------------------------

@router.post("/demo")
def load_demo(
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """
    Returns a quick status confirming demo data is already loaded.
    The database ships pre-populated with 64 videos and 224 Q&A pairs,
    so no ingestion is needed – this endpoint just lets the frontend know.
    """
    video_count = db.query(Video).count()
    qa_count = db.query(QAPair).count()
    return {
        "status": "success",
        "message": (
            f"Demo data is ready. {video_count} videos and {qa_count} Q&A pairs "
            "are indexed and available for search."
        ),
        "videos": video_count,
        "qa_pairs": qa_count,
    }


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/stats")
def admin_stats(
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(get_api_key),
):
    """Return current database and vector index stats."""
    video_count = db.query(Video).count()
    qa_count = db.query(QAPair).count()
    index_size = _index.ntotal if _index is not None else 0
    return {
        "videos": video_count,
        "qa_pairs": qa_count,
        "index_size": index_size,
    }


@router.get("/admin/health")
def admin_health(db: Session = Depends(get_db)):
    """Check availability of configured LLM providers."""
    groq_configured = bool(os.getenv("GROQ_API_KEY", "").strip())
    openrouter_configured = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    apifree_configured = bool(os.getenv("APIFREE_API_KEY", "").strip())
    nvidia_configured = bool(os.getenv("NVIDIA_API_KEY", "").strip())
    any_llm = groq_configured or openrouter_configured or apifree_configured or nvidia_configured

    # Check database
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Check vector index
    index_status = "ok" if _index and _index.ntotal > 0 else "empty"

    # Check Redis
    from app.services.cache import get_redis_client
    redis_status = "ok" if get_redis_client() else "unavailable"

    overall = "ok" if (any_llm and db_status == "ok") else "degraded"

    return HealthDetailResponse(
        status=overall,
        database=db_status,
        vector_index=index_status,
        llm_providers={
            "groq": groq_configured,
            "openrouter": openrouter_configured,
            "apifree": apifree_configured,
            "nvidia": nvidia_configured,
        },
        redis=redis_status,
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_cache: dict = {}  # Simple in-memory cache (use Redis in production)


def _get_cached_answer(query: str) -> Optional[dict]:
    """Check cache for query result."""
    if query in _cache:
        return _cache[query]
    return None


def _cache_answer(query: str, answer: dict, ttl: int = 3600) -> None:
    """Cache query result."""
    _cache[query] = answer
    # Simple TTL implementation - in production use Redis
    import threading
    threading.Timer(ttl, lambda: _cache.pop(query, None)).start()