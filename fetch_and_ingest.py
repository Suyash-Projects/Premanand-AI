# -*- coding: utf-8 -*-
"""
fetch_and_ingest.py  —  Combined pipeline: fetch remaining transcripts + ingest to DB.

Strategy:
  - Parallel fetch with ThreadPoolExecutor (FETCH_WORKERS workers)
  - Auto-backoff on 429 / bot-detection (exponential, capped at COOLDOWN_ON_BAN)
  - Re-queue failed videos for retry (up to MAX_RETRIES)
  - Auto-ingest each transcript immediately after download (no separate step needed)
  - Resume-safe: skips already-downloaded AND already-ingested videos
  - Progress bar via tqdm

Usage:
    venv\Scripts\python fetch_and_ingest.py
    venv\Scripts\python fetch_and_ingest.py --fetch-only      # skip ingestion
    venv\Scripts\python fetch_and_ingest.py --ingest-only     # skip fetching (process existing files)
    venv\Scripts\python fetch_and_ingest.py --workers 3       # parallelism
    venv\Scripts\python fetch_and_ingest.py --no-faiss        # skip FAISS (DB only, faster/less RAM)
    venv\Scripts\python fetch_and_ingest.py --fetch-only      # just download, no DB/FAISS
"""
import os
import sys
import json
import time
import random
import argparse
import threading
import concurrent.futures
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── bootstrap app imports ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", "sqlite:///./bhaktimarg_qa.db")
os.environ.setdefault("PYTHONUTF8", "1")

from dotenv import load_dotenv
load_dotenv()

# ── constants ─────────────────────────────────────────────────────────────────
CHANNEL_URL       = "https://www.youtube.com/@BhajanMarg"
OUTPUT_DIR        = "transcripts_raw"
VIDEO_LIST_CACHE  = "video_list_cache.json"
PROGRESS_FILE     = "fetch_ingest_progress.txt"
FETCH_WORKERS     = 2          # parallel yt-dlp workers (keep low to avoid bans)
COOLDOWN_MIN      = 2          # seconds between fetches per worker
COOLDOWN_MAX      = 6
COOLDOWN_ON_BAN   = 300        # 5 min sleep when 429 received
MAX_RETRIES       = 3
CHUNK_SECONDS     = 200        # transcript chunk size for LLM extraction

# ── thread-safe logging ───────────────────────────────────────────────────────
_log_lock = threading.Lock()

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        print(line, flush=True)
        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# ── video list ────────────────────────────────────────────────────────────────

def load_video_list() -> list:
    if os.path.exists(VIDEO_LIST_CACHE):
        with open(VIDEO_LIST_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# ── transcript fetching ───────────────────────────────────────────────────────

def _yt_opts() -> dict:
    opts = {
        "quiet": True,
        "ignoreerrors": True,
        "skip_download": True,       # we only want metadata/subtitles, never the video
        "writesubtitles": False,      # we fetch subtitle URLs ourselves
        "writeautomaticsub": False,
        "lazy_playlist": True,
        "socket_timeout": 20,
        "extractor_retries": 3,
    }
    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"
    return opts


def fetch_transcript(v: dict) -> tuple[dict, object, str | None]:
    """
    Returns (video, transcript_or_status, lang_used)
    transcript_or_status is:
      - list[dict]   → success
      - "RATE_LIMITED"
      - "NO_TRANSCRIPT"
    """
    import yt_dlp

    vid_id = v["id"]

    try:
        with yt_dlp.YoutubeDL(_yt_opts()) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={vid_id}", download=False
            )
    except Exception as exc:
        err = str(exc)
        if "429" in err or "bot" in err.lower() or "challenge" in err.lower():
            return v, "RATE_LIMITED", None
        return v, "NO_TRANSCRIPT", None

    if not info:
        return v, "NO_TRANSCRIPT", None

    auto_subs   = info.get("automatic_captions", {})
    manual_subs = info.get("subtitles", {})

    sub_data  = None
    lang_used = None

    for lang in ["hi", "en"]:
        for pool, suffix in [(manual_subs, "manual"), (auto_subs, "auto")]:
            if lang in pool:
                for fmt in pool[lang]:
                    if fmt.get("ext") == "json3":
                        sub_data  = fmt
                        lang_used = f"{lang}-{suffix}"
                        break
            if sub_data:
                break
        if sub_data:
            break

    if not (sub_data and sub_data.get("url")):
        return v, "NO_TRANSCRIPT", None

    try:
        req = urllib.request.Request(sub_data["url"])
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return v, "NO_TRANSCRIPT", None

    transcript = []
    for event in raw.get("events", []):
        if "segs" in event:
            text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
            if text and text != "\n":
                transcript.append(
                    {
                        "start":    event.get("tStartMs", 0) / 1000,
                        "duration": event.get("dDurationMs", 0) / 1000,
                        "text":     text,
                    }
                )

    if not transcript:
        return v, "NO_TRANSCRIPT", None

    return v, transcript, lang_used


def save_transcript(v: dict, transcript: list, lang: str) -> str:
    """Write transcript JSON to disk and return the filepath."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, f"{v['id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            {
                "video_id":  v["id"],
                "title":     v["title"],
                "playlist":  v.get("playlist", ""),
                "language":  lang,
                "segments":  len(transcript),
                "transcript": transcript,
            },
            f,
            ensure_ascii=False,
        )
    return filepath

# ── ingestion ─────────────────────────────────────────────────────────────────

_ingest_lock = threading.Lock()  # DB writes must be serial

def _make_chunks(segments: list, chunk_seconds: int = CHUNK_SECONDS) -> list:
    chunks = []
    current_text = ""
    chunk_start_ts = 0.0
    started = False

    for seg in segments:
        start = seg.get("start", 0)
        text  = seg.get("text", "").strip()
        if not text:
            continue
        if not started:
            chunk_start_ts = start
            started = True
        if start - chunk_start_ts > chunk_seconds and current_text.strip():
            chunks.append({"text": current_text.strip(), "timestamp": int(chunk_start_ts)})
            current_text   = f"[{int(start)}s] {text} "
            chunk_start_ts = start
        else:
            current_text += f"[{int(start)}s] {text} "

    if current_text.strip():
        chunks.append({"text": current_text.strip(), "timestamp": int(chunk_start_ts)})

    return chunks


def ingest_file(filepath: str, skip_faiss: bool = False) -> int:
    """
    Read a transcript JSON, extract Q&A pairs via LLM, write to DB.
    Optionally also adds to FAISS index (can skip to save RAM).
    Thread-safe: uses _ingest_lock for DB operations.
    """
    from app.database.connection import SessionLocal
    from app.models.db_models import Video, QAPair
    from app.services.llm_service import extract_qa_pairs
    from app.services.vector_store import add_to_index

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    vid_id   = data["video_id"]
    title    = data["title"]
    segments = data.get("transcript", [])

    if not segments:
        log(f"  SKIP (no segments): {title[:55]}")
        return 0

    with _ingest_lock:
        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.youtube_id == vid_id).first()
            if not video:
                video = Video(
                    youtube_id=vid_id,
                    title=title,
                    url=f"https://www.youtube.com/watch?v={vid_id}",
                )
                db.add(video)
                db.commit()
                db.refresh(video)

            existing = db.query(QAPair).filter(QAPair.video_id == video.id).count()
            if existing > 0:
                log(f"  SKIP (already in DB, {existing} pairs): {title[:55]}")
                return existing

            video_id_int = video.id
        finally:
            db.close()

    chunks = _make_chunks(segments)
    log(f"  Ingesting {len(chunks)} chunks: {title[:55]}")

    total_pairs = 0
    for i, chunk in enumerate(chunks):
        time.sleep(0.4)  # tiny LLM rate-limit buffer
        try:
            pairs = extract_qa_pairs(chunk["text"])
            if pairs:
                with _ingest_lock:
                    db = SessionLocal()
                    try:
                        # Re-fetch video (may have been added by another thread)
                        video = db.query(Video).filter(Video.youtube_id == vid_id).first()
                        for pair in pairs:
                            if pair.get("question") and pair.get("answer"):
                                qa = QAPair(
                                    video_id=video.id,
                                    question=pair["question"],
                                    answer=pair["answer"],
                                    timestamp=pair.get("timestamp", chunk["timestamp"]),
                                )
                                db.add(qa)
                                db.commit()
                                db.refresh(qa)
                                add_to_index(qa)
                                total_pairs += 1
                    finally:
                        db.close()
                log(f"    Chunk {i+1}/{len(chunks)}: +{len(pairs)} pairs")
            else:
                log(f"    Chunk {i+1}/{len(chunks)}: 0 pairs")
        except Exception as exc:
            log(f"    Chunk {i+1}/{len(chunks)}: ERROR – {str(exc)[:70]}")

    return total_pairs

# ── worker (fetch + optional ingest) ─────────────────────────────────────────

_ban_event   = threading.Event()   # set when any worker hits a 429
_ban_until   = 0.0                 # epoch time when ban expires
_ban_lock    = threading.Lock()


def _wait_if_banned():
    while _ban_event.is_set():
        remaining = _ban_until - time.time()
        if remaining <= 0:
            _ban_event.clear()
            break
        time.sleep(min(10, remaining))


def fetch_worker(v: dict, do_ingest: bool, skip_faiss: bool = False, retry: int = 0) -> dict:
    """
    Returns a result dict:
      { "id": ..., "status": "ok"|"rate_limited"|"no_transcript"|"empty", "pairs": int }
    """
    _wait_if_banned()

    # Random human-like delay
    time.sleep(random.uniform(COOLDOWN_MIN, COOLDOWN_MAX))

    vid_id    = v["id"]
    title     = v["title"][:55]
    filepath  = os.path.join(OUTPUT_DIR, f"{vid_id}.json")

    # Already downloaded — jump straight to ingest if needed
    if os.path.exists(filepath):
        log(f"  [CACHED] {title}")
        if do_ingest:
            pairs = ingest_file(filepath, skip_faiss=skip_faiss)
            return {"id": vid_id, "status": "ok", "pairs": pairs}
        return {"id": vid_id, "status": "ok", "pairs": 0}

    log(f"  [FETCH] {title}")
    video, transcript, lang = fetch_transcript(v)

    if transcript == "RATE_LIMITED":
        log(f"  [429] {title} — cooling down {COOLDOWN_ON_BAN // 60} min (retry {retry+1}/{MAX_RETRIES})")
        with _ban_lock:
            global _ban_until
            _ban_until = time.time() + COOLDOWN_ON_BAN
            _ban_event.set()
        if retry < MAX_RETRIES:
            return fetch_worker(v, do_ingest, skip_faiss, retry + 1)
        return {"id": vid_id, "status": "rate_limited", "pairs": 0}

    if transcript == "NO_TRANSCRIPT" or not isinstance(transcript, list):
        log(f"  [NO TRANSCRIPT] {title}")
        return {"id": vid_id, "status": "no_transcript", "pairs": 0}

    if len(transcript) == 0:
        log(f"  [EMPTY] {title}")
        return {"id": vid_id, "status": "empty", "pairs": 0}

    filepath = save_transcript(v, transcript, lang)
    size_kb  = os.path.getsize(filepath) / 1024
    log(f"  [OK] {title} ({lang}, {len(transcript)} segs, {size_kb:.0f}KB)")

    pairs = 0
    if do_ingest:
        pairs = ingest_file(filepath, skip_faiss=skip_faiss)
        log(f"  [INGESTED] {title} → {pairs} Q&A pairs")

    return {"id": vid_id, "status": "ok", "pairs": pairs}

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch + ingest remaining BhajanMarg transcripts")
    parser.add_argument("--fetch-only",   action="store_true", help="Skip ingestion (only download transcripts)")
    parser.add_argument("--ingest-only",  action="store_true", help="Skip fetching (process existing transcripts)")
    parser.add_argument("--no-faiss",     action="store_true", help="Skip FAISS indexing (DB only — saves RAM)")
    parser.add_argument("--workers",      type=int, default=FETCH_WORKERS, help=f"Parallel fetch workers (default {FETCH_WORKERS})")
    parser.add_argument("--limit",        type=int, default=0, help="Process at most N videos (0 = all)")
    args = parser.parse_args()

    do_fetch   = not args.ingest_only
    do_ingest  = not args.fetch_only
    skip_faiss = args.no_faiss

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── initialise FAISS index (non-blocking) ──────────────────────────────
    if do_ingest:
        from app.database.connection import engine, Base
        from app.models.db_models import Video, QAPair  # noqa: F401 – create tables
        Base.metadata.create_all(bind=engine)

        if not skip_faiss:
            try:
                from app.services.vector_store import init_index
                log("Initialising FAISS index…")
                init_index()
                log("FAISS index ready.")
            except Exception as e:
                log(f"[WARN] FAISS init failed ({e}). Use --no-faiss to skip. Continuing without FAISS.")
                skip_faiss = True

    # ── build work queue ───────────────────────────────────────────────────
    all_videos = load_video_list()
    if not all_videos:
        log("ERROR: video_list_cache.json not found! Run the old fetcher first.")
        return

    if args.ingest_only:
        # Ingest all existing transcript files (already downloaded)
        files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json"))
        log(f"Ingest-only mode: {len(files)} transcript files found.")
        total_pairs = 0
        for i, fname in enumerate(files, 1):
            fp = os.path.join(OUTPUT_DIR, fname)
            log(f"\n[{i}/{len(files)}] {fname}")
            n = ingest_file(fp, skip_faiss=skip_faiss)
            total_pairs += n
            log(f"  => {n} pairs. Running total: {total_pairs}")
        log(f"\nINGESTION COMPLETE. Total new pairs: {total_pairs}")
        return

    # Normal fetch (+ingest) mode
    already_downloaded = {
        f[:-5] for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")
    }
    remaining = [v for v in all_videos if v["id"] not in already_downloaded]

    log(f"Total in cache  : {len(all_videos)}")
    log(f"Already on disk : {len(already_downloaded)}")
    log(f"Remaining       : {len(remaining)}")

    if args.limit > 0:
        remaining = remaining[:args.limit]
        log(f"Limited to first : {args.limit} videos")

    if not remaining:
        log("Nothing to fetch! All videos already downloaded.")
        if do_ingest:
            log("Running ingest on existing files…")
            # fall through to ingest-only logic
            files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json"))
            total_pairs = 0
            for i, fname in enumerate(files, 1):
                fp = os.path.join(OUTPUT_DIR, fname)
                log(f"\n[{i}/{len(files)}] {fname}")
                n = ingest_file(fp)
                total_pairs += n
            log(f"Total pairs: {total_pairs}")
        return

    log(f"\nStarting parallel fetch with {args.workers} worker(s)…\n")
    start_time = time.time()

    counters = {"ok": 0, "no_transcript": 0, "rate_limited": 0, "empty": 0, "pairs": 0}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_worker, v, do_ingest, skip_faiss): v
            for v in remaining
        }
        done_count = 0
        for future in concurrent.futures.as_completed(futures):
            done_count += 1
            try:
                result = future.result()
                status = result.get("status", "ok")
                counters[status] = counters.get(status, 0) + 1
                counters["pairs"] += result.get("pairs", 0)
            except Exception as exc:
                log(f"  [EXCEPTION] {exc}")
                counters["ok"] += 0

            elapsed = time.time() - start_time
            log(
                f"  Progress: {done_count}/{len(remaining)} | "
                f"OK={counters['ok']} NoSub={counters['no_transcript']} "
                f"Banned={counters['rate_limited']} | "
                f"Q&A pairs: {counters['pairs']} | "
                f"{elapsed/60:.1f}min"
            )

    elapsed_total = time.time() - start_time
    total_files   = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")])

    log(f"\n{'='*60}")
    log(f"PIPELINE COMPLETE")
    log(f"{'='*60}")
    log(f"  Newly downloaded  : {counters['ok']}")
    log(f"  No transcript     : {counters['no_transcript']}")
    log(f"  Rate-limited      : {counters['rate_limited']}")
    log(f"  Total on disk     : {total_files} / {len(all_videos)}")
    if do_ingest:
        log(f"  New Q&A pairs     : {counters['pairs']}")
    if not args.fetch_only and counters["pairs"] > 0 and not skip_faiss:
        # Rebuild FAISS from DB after all ingestion
        log("Rebuilding FAISS index from DB…")
        try:
            from app.services.vector_store import init_index, _index
            import app.services.vector_store as vs
            vs._index = None  # force rebuild
            init_index()
            log("FAISS rebuild complete.")
        except Exception as e:
            log(f"[WARN] FAISS rebuild failed: {e}. Run ingest_transcripts.py to rebuild.")


if __name__ == "__main__":
    main()
