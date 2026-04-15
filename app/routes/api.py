from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database.connection import get_db
from app.models.db_models import Video, QAPair
from app.services.rag_pipeline import process_query
from app.services.vector_store import add_to_index
from app.services.youtube_service import process_channel_videos

router = APIRouter()

class QueryRequest(BaseModel):
    query: str

class VideoResponse(BaseModel):
    id: int
    title: str
    youtube_id: str
    url: str

class QAResponse(BaseModel):
    id: int
    question: str
    answer: str
    timestamp: int
    video_id: int

@router.post("/ask")
def ask_question(request: QueryRequest, db: Session = Depends(get_db)):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    answer_data = process_query(request.query)
    return answer_data

@router.get("/videos", response_model=List[VideoResponse])
def get_videos(db: Session = Depends(get_db)):
    videos = db.query(Video).all()
    return videos

@router.get("/qa", response_model=List[QAResponse])
def get_qa(db: Session = Depends(get_db)):
    pairs = db.query(QAPair).all()
    return pairs

@router.post("/process-channel")
def process_channel(background_tasks: BackgroundTasks, max_videos: int = 10, db: Session = Depends(get_db)):
    """Triggers the full ETL pipeline to scrape, extract, and index QAs from the channel."""
    background_tasks.add_task(process_channel_videos, db, max_videos)
    return {"status": "success", "message": f"Processing of up to {max_videos} videos started in the background."}
