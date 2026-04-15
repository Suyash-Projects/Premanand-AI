import logging
from typing import List
from sqlalchemy.orm import Session
from youtube_transcript_api import YouTubeTranscriptApi
from app.models.db_models import Video, QAPair
from app.database.connection import get_db
from app.services.llm_service import extract_qa_pairs
from app.services.vector_store import add_to_index
import yt_dlp
import traceback

logger = logging.getLogger(__name__)

CHANNEL_URL = "https://www.youtube.com/@BhajanMarg"

def fetch_latest_videos(max_count: int = 10) -> List[dict]:
    """Uses yt-dlp to fetch the latest video metadata from the channel."""
    logger.info(f"Fetching latest {max_count} videos from {CHANNEL_URL}")
    ydl_opts = {
        'extract_flat': True,
        'playlist_items': f'1-{max_count}',
        'quiet': True,
        'ignoreerrors': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(CHANNEL_URL, download=False)
        if 'entries' in result:
            # yt-dlp returns entries which contain video 'id', 'title', 'url'
            videos = []
            for entry in result['entries']:
                if entry and entry.get('id'):
                    videos.append({
                        "id": entry['id'],
                        "title": entry.get('title', 'Unknown Title'),
                        "url": entry.get('url', f"https://www.youtube.com/watch?v={entry['id']}")
                    })
            return videos
    return []

def get_transcript_chunks(video_id: str, chunk_duration: int = 180) -> List[str]:
    """Fetches Hindi/Auto-Hindi transcript and groups text into physical chunks with timestamps."""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['hi'])
    except Exception as e:
        logger.warning(f"Could not fetch transcript for {video_id}: {e}")
        return []

    chunks = []
    current_chunk = ""
    current_chunk_start = 0
    
    for item in transcript:
        # e.g. [45s] यह प्रश्न है...
        text_with_timestamp = f"[{int(item['start'])}s] {item['text']} "
        
        if item['start'] - current_chunk_start > chunk_duration:
            if current_chunk.strip():
                chunks.append(current_chunk)
            current_chunk = text_with_timestamp
            current_chunk_start = item['start']
        else:
            current_chunk += text_with_timestamp
            
    if current_chunk.strip():
        chunks.append(current_chunk)
        
    return chunks

def process_channel_videos(db: Session, max_videos: int = 10) -> dict:
    """End-to-End pipeline to fetch videos, pull transcripts, extract QA via LLM, and index them."""
    videos = fetch_latest_videos(max_count=max_videos)
    logger.info(f"Found {len(videos)} videos.")
    
    total_qa_extracted = 0
    
    for v in videos:
        # Check if video already in db
        existing_vid = db.query(Video).filter(Video.youtube_id == v['id']).first()
        if not existing_vid:
            db_video = Video(youtube_id=v['id'], title=v['title'], url=v['url'])
            db.add(db_video)
            db.commit()
            db.refresh(db_video)
        else:
            db_video = existing_vid
            
        logger.info(f"Processing Video: {v['title']} ({v['id']})")
        chunks = get_transcript_chunks(v['id'])
        
        video_qa_pairs = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  Extracting QA from chunk {i+1}/{len(chunks)}")
            extracted_pairs = extract_qa_pairs(chunk)
            
            for pair in extracted_pairs:
                if 'question' in pair and 'answer' in pair:
                    db_qa = QAPair(
                        video_id=db_video.id,
                        question=pair['question'],
                        answer=pair['answer'],
                        timestamp=pair.get('timestamp', 0)
                    )
                    db.add(db_qa)
                    db.commit()
                    db.refresh(db_qa)
                    video_qa_pairs.append(db_qa)
                    add_to_index(db_qa)
                    total_qa_extracted += 1
            
    return {"status": "success", "videos_processed": len(videos), "total_qa_extracted": total_qa_extracted}
