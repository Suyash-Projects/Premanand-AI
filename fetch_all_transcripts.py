# -*- coding: utf-8 -*-
"""
Fetch transcripts and extract Q&A for BhajanMarg channel.
Uses youtube-transcript-api for reliable transcript fetching.
"""
import os
import sys
import json
import time
import logging
import urllib.request

os.environ["PYTHONUTF8"] = "1"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

from app.database.connection import SessionLocal, engine, Base
from app.models.db_models import Video, QAPair
from app.services.vector_store import add_to_index, init_index
from app.services.llm_service import extract_qa_pairs

PROGRESS_FILE = "extraction_full.txt"


def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    logger.info(msg)


def get_transcript_with_yttapi(video_id):
    """Fetch transcript using youtube-transcript-api with Hindi/English priority."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable
    )

    try:
        # Try Hindi first, then English
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=['hi', 'en', 'hn']
        )
        return [
            {"start": item['start'], "text": item['text']}
            for item in transcript
        ]
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        log(f"  No transcript available: {video_id} - {e}")
        return None
    except Exception as e:
        log(f"  Transcript fetch error: {video_id} - {e}")
        return None


def get_transcript_fallback(video_id):
    """Fallback to yt-dlp extraction."""
    import yt_dlp

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'writeautomaticsub': True,
    }
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

            # Try manual subtitles first, then auto
            subs = info.get('subtitles', {}) or info.get('automatic_captions', {})

            for lang in ['hi', 'en', 'hn']:
                if lang in subs:
                    for fmt in subs[lang]:
                        if fmt.get('ext') == 'json3':
                            sub_url = fmt.get('url')
                            if sub_url:
                                req = urllib.request.Request(sub_url, headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                })
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    raw = json.loads(resp.read().decode("utf-8"))
                                    transcript = []
                                    for event in raw.get("events", []):
                                        if "segs" in event:
                                            text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
                                            if text:
                                                start = event.get("tStartMs", 0) / 1000
                                                transcript.append({"start": start, "text": text})
                                    if transcript:
                                        return transcript
        return None
    except Exception as e:
        log(f"  yt-dlp fallback error: {e}")
        return None


def chunk_transcript(transcript, duration=180):
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


def process_missing_videos():
    """Process videos that don't have QA pairs yet."""
    log("=" * 60)
    log("STARTING FULL TRANSCRIPT EXTRACTION")
    log("=" * 60)

    Base.metadata.create_all(bind=engine)
    init_index()

    db = SessionLocal()

    # Get all videos
    all_videos = db.query(Video).all()
    log(f"Total videos in DB: {len(all_videos)}")

    # Find videos without QA
    videos_with_qa = {v[0] for v in db.query(QAPair.video_id).distinct().all()}
    missing = [v for v in all_videos if v.id not in videos_with_qa]
    log(f"Videos needing extraction: {len(missing)}")

    total_qa = 0
    no_transcript = []
    errors = []

    for i, video in enumerate(missing):
        log(f"[{i+1}/{len(missing)}] {video.title[:50]}...")

        # Try youtube-transcript-api first
        transcript = get_transcript_with_yttapi(video.youtube_id)

        # Fallback to yt-dlp
        if not transcript:
            transcript = get_transcript_fallback(video.youtube_id)

        if not transcript:
            no_transcript.append(video.youtube_id)
            log(f"  [X] No transcript")
            continue

        # Chunk and extract
        chunks = chunk_transcript(transcript)
        log(f"  [+ve] {len(chunks)} segments")

        video_qa = 0
        for j, chunk in enumerate(chunks):
            time.sleep(0.5)  # Rate limiting

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
                        add_to_index(qa)
                        video_qa += 1
                        total_qa += 1

        if video_qa > 0:
            log(f"  [OK] {video_qa} QA pairs extracted")
        else:
            log(f"  [-] No QA pairs found")

        # Progress every 20 videos
        if (i + 1) % 20 == 0:
            log(f">>> Progress: {i+1}/{len(missing)} | Total QA: {total_qa}")

    # Summary
    log("=" * 60)
    log("EXTRACTION COMPLETE")
    log(f"Videos processed: {len(missing)}")
    log(f"Videos without transcripts: {len(no_transcript)}")
    log(f"Total Q&A pairs: {db.query(QAPair).count()}")
    log("=" * 60)

    if no_transcript:
        log(f"Videos without transcripts (first 20):")
        for vid in no_transcript[:20]:
            log(f"  - {vid}")

    db.close()
    return total_qa


if __name__ == "__main__":
    process_missing_videos()