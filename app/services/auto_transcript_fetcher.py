# -*- coding: utf-8 -*-
"""
Automatic transcript fetcher - runs in background to ensure all videos have transcripts.
Detects missing transcripts and fetches them automatically.
"""
import os
import sys
import time
import json
import logging
import urllib.request
from typing import Optional

import yt_dlp

from app.database.connection import SessionLocal, engine, Base
from app.models.db_models import Video, QAPair
from app.services.vector_store import add_to_index
from app.services.llm_service import extract_qa_pairs

logger = logging.getLogger(__name__)

PROGRESS_FILE = "auto_fetch_progress.txt"


def log(msg: str):
    """Log to file and console."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass
    logger.info(msg)


def get_transcript(video_id: str) -> Optional[list]:
    """Get transcript using multiple methods - returns list of {start, text} dicts."""

    # Method 1: youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
        )

        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=['hi', 'en', 'hn']
        )
        return [{"start": item['start'], "text": item['text']} for item in transcript]
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        pass
    except Exception as e:
        log(f"yttapi error: {e}")

    # Method 2: yt-dlp with auto subtitles
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'writeautomaticsub': True,
        'socket_timeout': 30,
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False
            )

            if not info:
                return None

            # Try manual then auto subtitles
            subs = info.get('subtitles') or info.get('automatic_captions') or {}

            for lang in ['hi', 'en', 'hn']:
                if lang in subs:
                    for fmt in subs[lang]:
                        if fmt.get('ext') == 'json3':
                            sub_url = fmt.get('url')
                            if sub_url:
                                req = urllib.request.Request(
                                    sub_url,
                                    headers={
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                    }
                                )
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    raw = json.loads(resp.read().decode("utf-8"))
                                    transcript = []
                                    for event in raw.get("events", []):
                                        if "segs" in event:
                                            text = "".join(
                                                seg.get("utf8", "") for seg in event["segs"]
                                            ).strip()
                                            if text:
                                                start = event.get("tStartMs", 0) / 1000
                                                transcript.append({"start": start, "text": text})
                                    if transcript:
                                        return transcript
        return None
    except Exception as e:
        log(f"yt-dlp error: {e}")
        return None


def chunk_transcript(transcript: list, duration: int = 180) -> list:
    """Group transcript into chunks."""
    if not transcript:
        return []

    chunks = []
    current = ""
    current_start = 0

    for item in transcript:
        text = f"[{int(item['start'])}s] {item['text']} "
        if item['start'] - current_start > duration:
            if current.strip():
                chunks.append(current)
            current = text
            current_start = item['start']
        else:
            current += text

    if current.strip():
        chunks.append(current)

    return chunks


def fetch_missing_transcripts(max_videos: int = None):
    """
    Main function to fetch missing transcripts and extract QA pairs.
    Call this on app startup or via cron job.
    """
    log("=" * 60)
    log("AUTO TRANSCRIPT FETCHER STARTED")
    log("=" * 60)

    # Ensure DB tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Get all video IDs that already have QA pairs
        videos_with_qa = {v[0] for v in db.query(QAPair.video_id).distinct().all()}
        all_videos = db.query(Video).all()

        log(f"Total videos: {len(all_videos)}")
        log(f"Videos with QA pairs: {len(videos_with_qa)}")

        # Filter to only videos without QA pairs
        missing_videos = [v for v in all_videos if v.id not in videos_with_qa]
        log(f"Videos needing extraction: {len(missing_videos)}")

        if max_videos:
            missing_videos = missing_videos[:max_videos]
            log(f"Processing max {max_videos} videos")

        total_qa = 0
        total_videos = len(missing_videos)
        no_transcript = []
        errors = []

        for i, video in enumerate(missing_videos):
            log(f"[{i+1}/{total_videos}] {video.title[:60]}...")

            # Get transcript
            transcript = get_transcript(video.youtube_id)

            if not transcript:
                no_transcript.append(video.youtube_id)
                log(f"  [X] No transcript available")
                continue

            # Chunk and extract QA
            chunks = chunk_transcript(transcript)
            log(f"  [+transcript] {len(chunks)} segments")

            video_qa = 0
            for j, chunk in enumerate(chunks):
                # Rate limiting for LLM API
                time.sleep(0.5)

                pairs = extract_qa_pairs(chunk)
                if pairs:
                    for pair in pairs:
                        if 'question' in pair and 'answer' in pair:
                            ts = pair.get('timestamp', 0)
                            if isinstance(ts, str):
                                ts = int(''.join(filter(str.isdigit, ts)) or '0')

                            qa = QAPair(
                                video_id=video.id,
                                question=pair['question'],
                                answer=pair['answer'],
                                timestamp=ts
                            )
                            db.add(qa)
                            db.commit()
                            db.refresh(qa)

                            try:
                                add_to_index(qa)
                            except Exception as e:
                                log(f"  Index error: {e}")

                            video_qa += 1
                            total_qa += 1

            if video_qa > 0:
                log(f"  [OK] Extracted {video_qa} QA pairs")
            else:
                log(f"  [-] No QA pairs found in transcript")

            # Progress every 50 videos
            if (i + 1) % 50 == 0:
                log(f">>> PROGRESS: {i+1}/{total_videos} | Total QA: {total_qa}")

        # Summary
        log("=" * 60)
        log("AUTO FETCH COMPLETE")
        log(f"Processed: {total_videos} videos")
        log(f"Total Q&A extracted: {total_qa}")
        log(f"Videos without transcripts: {len(no_transcript)}")
        log(f"Total in DB now: {db.query(QAPair).count()} Q&A pairs")
        log("=" * 60)

        if no_transcript:
            log(f"Videos without transcripts (first 30):")
            for vid in no_transcript[:30]:
                log(f"  - {vid}")

    finally:
        db.close()

    return total_qa


# CLI entrypoint
if __name__ == "__main__":
    os.environ["PYTHONUTF8"] = "1"
    fetch_missing_transcripts()