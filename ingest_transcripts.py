"""
Fast direct ingestion of transcripts_raw/*.json into the database.
Bypasses YouTube entirely — reads local cache, extracts Q&A via LLM, builds FAISS index.
Run: venv\Scripts\python.exe ingest_transcripts.py
"""
import os
import sys
import json
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Bootstrap Django-style path so app imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", "sqlite:///./bhaktimarg_qa.db")

from dotenv import load_dotenv
load_dotenv()

from app.database.connection import SessionLocal, engine, Base
from app.models.db_models import Video, QAPair
from app.services.llm_service import extract_qa_pairs
from app.services.vector_store import add_to_index, init_index

TRANSCRIPTS_DIR = "transcripts_raw"
CHUNK_SECONDS = 200   # group transcript segments into ~3-min chunks
PROGRESS_FILE = "ingest_progress.txt"

Base.metadata.create_all(bind=engine)

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True, end='\n')
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def make_chunks(segments, chunk_seconds=CHUNK_SECONDS):
    """Group transcript segments into text chunks of ~chunk_seconds each."""
    chunks = []
    current_text = ""
    current_start = None
    chunk_start_ts = 0

    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue

        if current_start is None:
            current_start = start
            chunk_start_ts = start

        if start - chunk_start_ts > chunk_seconds and current_text.strip():
            chunks.append({"text": current_text.strip(), "timestamp": int(chunk_start_ts)})
            current_text = f"[{int(start)}s] {text} "
            chunk_start_ts = start
        else:
            current_text += f"[{int(start)}s] {text} "

    if current_text.strip():
        chunks.append({"text": current_text.strip(), "timestamp": int(chunk_start_ts)})

    return chunks

def ingest_file(filepath, db):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    vid_id = data["video_id"]
    title = data["title"]
    playlist = data.get("playlist", "")
    segments = data.get("transcript", [])

    if not segments:
        log(f"  SKIP (no segments): {title[:50]}")
        return 0

    # Upsert video record
    video = db.query(Video).filter(Video.youtube_id == vid_id).first()
    if not video:
        video = Video(
            youtube_id=vid_id,
            title=title,
            url=f"https://www.youtube.com/watch?v={vid_id}"
        )
        db.add(video)
        db.commit()
        db.refresh(video)

    # Check if already processed
    existing = db.query(QAPair).filter(QAPair.video_id == video.id).count()
    if existing > 0:
        log(f"  SKIP (already in DB, {existing} pairs): {title[:50]}")
        return existing

    chunks = make_chunks(segments)
    log(f"  Processing {len(chunks)} chunks from: {title[:55]}")

    total_pairs = 0
    for i, chunk in enumerate(chunks):
        time.sleep(0.5)  # small LLM rate-limit buffer
        try:
            pairs = extract_qa_pairs(chunk["text"])
            if pairs:
                for pair in pairs:
                    if pair.get("question") and pair.get("answer"):
                        qa = QAPair(
                            video_id=video.id,
                            question=pair["question"],
                            answer=pair["answer"],
                            timestamp=pair.get("timestamp", chunk["timestamp"])
                        )
                        db.add(qa)
                        db.commit()
                        db.refresh(qa)
                        add_to_index(qa)
                        total_pairs += 1
                log(f"    Chunk {i+1}/{len(chunks)}: +{len(pairs)} pairs")
            else:
                log(f"    Chunk {i+1}/{len(chunks)}: 0 pairs")
        except Exception as e:
            log(f"    Chunk {i+1}/{len(chunks)}: ERROR - {str(e)[:60]}")

    return total_pairs

def main():
    if not os.path.exists(TRANSCRIPTS_DIR):
        log("ERROR: transcripts_raw/ folder not found!")
        return

    files = [f for f in sorted(os.listdir(TRANSCRIPTS_DIR)) if f.endswith(".json")]
    log(f"Found {len(files)} transcript files to ingest.")

    # Initialize FAISS index
    init_index()

    db = SessionLocal()
    grand_total = 0
    start_time = time.time()

    try:
        for idx, fname in enumerate(files, 1):
            filepath = os.path.join(TRANSCRIPTS_DIR, fname)
            log(f"\n[{idx}/{len(files)}] {fname}")
            n = ingest_file(filepath, db)
            grand_total += n
            elapsed = time.time() - start_time
            log(f"  => {n} new Q&A pairs. Total so far: {grand_total}. Elapsed: {elapsed/60:.1f}min")
    finally:
        db.close()

    log(f"\n{'='*55}")
    log(f"INGESTION COMPLETE")
    log(f"Total Q&A pairs added: {grand_total}")
    log(f"Total time: {(time.time()-start_time)/60:.1f} minutes")
    log(f"{'='*55}")
    log(f"\nThe app is now ready! Start it with: uvicorn app.main:app --reload")

if __name__ == "__main__":
    main()
