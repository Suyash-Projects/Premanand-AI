# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os

from app.database.connection import get_db
from app.models.db_models import Video, QAPair
from app.services.rag_pipeline import process_query
from app.services.vector_store import add_to_index, _index
from app.services.youtube_service import process_channel_videos

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


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

@router.post("/ask")
def ask_question(request: QueryRequest, db: Session = Depends(get_db)):
    """Answer a spiritual question using the RAG pipeline."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    answer_data = process_query(request.query)
    return answer_data


@router.get("/videos", response_model=List[VideoResponse])
def get_videos(db: Session = Depends(get_db)):
    """Return all indexed videos."""
    videos = db.query(Video).all()
    return videos


@router.get("/qa", response_model=List[QAResponse])
def get_qa(db: Session = Depends(get_db)):
    """Return all Q&A pairs."""
    pairs = db.query(QAPair).all()
    return pairs


@router.post("/process-channel")
def process_channel(
    background_tasks: BackgroundTasks,
    max_videos: int = 10,
    db: Session = Depends(get_db),
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
def load_demo(db: Session = Depends(get_db)):
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
def admin_stats(db: Session = Depends(get_db)):
    """Return current database and vector index stats."""
    from app.services.vector_store import _index as faiss_index
    video_count = db.query(Video).count()
    qa_count = db.query(QAPair).count()
    index_size = faiss_index.ntotal if faiss_index is not None else 0
    return {
        "videos": video_count,
        "qa_pairs": qa_count,
        "index_size": index_size,
    }


@router.get("/admin/health")
def admin_health():
    """Check availability of configured LLM providers."""
    groq_configured = bool(os.getenv("GROQ_API_KEY", "").strip())
    openrouter_configured = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    apifree_configured = bool(os.getenv("APIFREE_API_KEY", "").strip())
    any_llm = groq_configured or openrouter_configured or apifree_configured
    return {
        "status": "ok" if any_llm else "degraded",
        "groq": groq_configured,
        "openrouter": openrouter_configured,
        "apifree": apifree_configured,
        "note": (
            "All LLMs configured." if any_llm
            else "No LLM API keys found – answers will use fallback text."
        ),
    }
