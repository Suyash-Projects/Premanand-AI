# -*- coding: utf-8 -*-
"""
RAG pipeline: retrieve → deduplicate → rank → generate.

Improvements:
- Deduplicates by (video_id, timestamp) so we never send duplicate context blocks.
- References are sorted by similarity score (highest first).
- Context string is capped at MAX_CONTEXT_CHARS to stay within LLM token limits.
- Hindi fallback message used when no results pass the similarity threshold.
"""
from app.services.vector_store import search_similar_qa
from app.services.llm_service import generate_answer
import logging

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 4_000  # ~1 000 tokens; safe for all supported models


def build_youtube_url(video_url: str, timestamp: int) -> str:
    """Build a YouTube URL with a timestamp parameter."""
    video_id = None
    if "watch?v=" in video_url:
        video_id = video_url.split("watch?v=")[-1].split("&")[0]
    elif "youtu.be/" in video_url:
        video_id = video_url.split("youtu.be/")[-1].split("?")[0]

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}&t={timestamp}s"
    return video_url


def format_timestamp(seconds: int) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def process_query(query: str) -> dict:
    # 1. Retrieve similar Q&A pairs (already sorted by score desc, threshold-filtered)
    similar_pairs = search_similar_qa(query, top_k=5)

    if not similar_pairs:
        return {
            "answer": (
                "क्षमा करें, मुझे इस प्रश्न का उत्तर मेरे पास उपलब्ध सामग्री में नहीं मिला। "
                "पूर्ण सत्य जानने के लिए कृपया महाराज जी के प्रवचन सुनें।"
            ),
            "references": [],
            "reference": None,
        }

    # 2. Deduplicate by (video_id, timestamp) and build context + references
    context_lines: list[str] = []
    references: list[dict] = []
    seen_keys: set[tuple] = set()
    total_chars = 0

    for p in similar_pairs:
        dedup_key = (getattr(p, "video_id", None), p.timestamp)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        block = f"Q: {p.question}\nA: {p.answer}"

        # Stop adding context once we'd exceed the character cap
        if total_chars + len(block) > MAX_CONTEXT_CHARS:
            logger.debug("Context cap reached at %d chars; stopping.", total_chars)
            break

        context_lines.append(block)
        total_chars += len(block)

        # Build reference (one per unique video, sorted by score via insertion order)
        if getattr(p, "video", None) and p.video is not None:
            ts = p.timestamp or 0
            ref_url = build_youtube_url(p.video.url, ts)
            references.append(
                {
                    "video_title": p.video.title,
                    "video_id": p.video.youtube_id,
                    "timestamp": ts,
                    "timestamp_str": format_timestamp(ts),
                    "url": ref_url,
                    "embed_url": f"https://www.youtube.com/embed/{p.video.youtube_id}?start={ts}",
                    "score": round(getattr(p, "score", 0.0), 4),
                }
            )

    # References are already in score-desc order (FAISS returns highest-score first)
    context = "\n---\n".join(context_lines)

    # 3. Generate answer via LLM (Hindi enforced in system prompt)
    answer = generate_answer(query, context)

    return {
        "answer": answer,
        "references": references,
        # Keep old key for backward compatibility with any cached clients
        "reference": references[0] if references else None,
    }
