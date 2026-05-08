import logging
import json
import urllib.request
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.db_models import Video, QAPair
from app.database.connection import get_db
from app.services.llm_service import extract_qa_pairs
from app.services.vector_store import add_to_index
import yt_dlp
import traceback
import os
import time
import random

logger = logging.getLogger(__name__)

CHANNEL_URL = "https://www.youtube.com/@BhajanMarg"
PROGRESS_FILE = "extraction_progress.txt"

def log_progress(msg: str):
    """Helper to write visible progress to a text file for the user."""
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    logger.info(msg)

def _get_yt_opts() -> dict:
    opts = {
        "quiet": True,
        "ignoreerrors": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "socket_timeout": 30,
        "extractor_retries": 5,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"
    return opts

def fetch_latest_videos(max_count: int = 10) -> List[dict]:
    """Uses yt-dlp to fetch the latest video metadata from the channel."""
    logger.info(f"Fetching latest {max_count} videos from {CHANNEL_URL}")
    ydl_opts = _get_yt_opts()
    ydl_opts['extract_flat'] = True
    ydl_opts['playlist_items'] = f'1-{max_count}'
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(CHANNEL_URL, download=False)
        if 'entries' in result:
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

def get_stealth_transcript(video_id: str) -> Tuple[Optional[List[dict]], Optional[str]]:
    """Fetches transcript using stealthy headers and priority selection (Manual -> Auto)."""
    try:
        with yt_dlp.YoutubeDL(_get_yt_opts()) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception as exc:
        logger.error(f"yt-dlp error for {video_id}: {exc}")
        return None, None

    if not info:
        return None, None

    auto_subs = info.get("automatic_captions", {})
    manual_subs = info.get("subtitles", {})
    sub_data = None
    lang_used = None

    priority = [
        ("hi", manual_subs, "manual"),
        ("hi", auto_subs, "auto"),
        ("en", manual_subs, "manual"),
        ("en", auto_subs, "auto")
    ]

    for lang, pool, suffix in priority:
        if lang in pool:
            for fmt in pool[lang]:
                if fmt.get("ext") == "json3":
                    sub_data = fmt
                    lang_used = f"{lang}-{suffix}"
                    break
        if sub_data:
            break

    if not (sub_data and sub_data.get("url")):
        return None, None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Referer": f"https://www.youtube.com/watch?v={video_id}",
            "Origin": "https://www.youtube.com"
        }
        req = urllib.request.Request(sub_data["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        
        transcript = []
        for event in raw.get("events", []):
            if "segs" in event:
                text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
                if text and text != "\n":
                    transcript.append({
                        "start": event.get("tStartMs", 0) / 1000,
                        "text": text,
                    })
        return transcript, lang_used
    except Exception as e:
        logger.error(f"Transcript fetch error for {video_id}: {e}")
        return None, None

def get_transcript_chunks(video_id: str, chunk_duration: int = 180) -> List[str]:
    """Fetches transcript and groups text into physical chunks with timestamps."""
    transcript, lang = get_stealth_transcript(video_id)
    if not transcript:
        return []

    chunks = []
    current_chunk = ""
    current_chunk_start = 0
    
    for item in transcript:
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

def process_channel_videos(db: Session, max_videos: int = 100) -> dict:
    """End-to-End pipeline to fetch videos, pull transcripts, extract QA via LLM, and index them."""
    log_progress(f"--- STARTING EXTRACTION FOR {max_videos} VIDEOS ---")
    videos = fetch_latest_videos(max_count=max_videos)
    log_progress(f"Found {len(videos)} total videos to scan.")
    
    total_qa_extracted = 0
    videos_with_content = 0
    
    for v in videos:
        log_progress(f"Scanning Video: {v['title']}")
        # Check if video already in db
        existing_vid = db.query(Video).filter(Video.youtube_id == v['id']).first()
        if not existing_vid:
            db_video = Video(youtube_id=v['id'], title=v['title'], url=v['url'])
            db.add(db_video)
            db.commit()
            db.refresh(db_video)
        else:
            db_video = existing_vid
            
        chunks = get_transcript_chunks(v['id'])
        
        if not chunks:
            log_progress(f"  [X] No transcript found. Skipping.")
            continue
            
        log_progress(f"  [+] Found {len(chunks)} transcript segments. Processing...")
        video_qa_pairs = []
        for i, chunk in enumerate(chunks):
            log_progress(f"    -> Extracting from segment {i+1}/{len(chunks)}...")
            time.sleep(1) # Safety delay
            
            extracted_pairs = extract_qa_pairs(chunk)
            
            if extracted_pairs:
                log_progress(f"      - Extracted {len(extracted_pairs)} QA pairs from segment.")
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
            else:
                log_progress(f"      - No distinct QA pairs found in this segment.")
        
        if video_qa_pairs:
            videos_with_content += 1
            log_progress(f"  [SUCCESS] Total QA pairs for this video: {len(video_qa_pairs)}")
            
    log_progress(f"--- EXTRACTION COMPLETE ---")
    log_progress(f"Extracted {total_qa_extracted} total pairs from {videos_with_content} videos.")
    
    return {
        "status": "success", 
        "videos_processed": len(videos), 
        "videos_with_content": videos_with_content,
        "total_qa_extracted": total_qa_extracted
    }
