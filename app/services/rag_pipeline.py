# -*- coding: utf-8 -*-
"""
Direct Transcript RAG: retrieves and presents original Q&A pairs.
Ensures 100% fidelity to Maharaj ji's actual words by avoiding AI summarization.
"""
from app.services.vector_store import search_similar_qa
import logging

logger = logging.getLogger(__name__)

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


def format_timestamp(seconds) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format. Handles numeric strings with suffixes like '2118s'."""
    try:
        if isinstance(seconds, str):
            # Clean string: keep only digits
            seconds = "".join(filter(str.isdigit, seconds))
        seconds = int(seconds or 0)
    except (ValueError, TypeError):
        seconds = 0
        
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def process_query(query: str) -> dict:
    """
    Retrieves multiple relevant segments and uses the LLM to synthesize a 
    broad, detailed answer that includes examples from Maharaj ji's words.
    """
    # 1. Retrieve more pairs to get a broader perspective (top_k=8)
    similar_pairs = search_similar_qa(query, top_k=8)

    if not similar_pairs:
        return {
            "answer": (
                "क्षमा करें, मुझे इस प्रश्न का उत्तर मेरे पास उपलब्ध महाराज जी के वचनों में नहीं मिला। "
                "कृपया किसी अन्य शब्द या प्रश्न के साथ प्रयास करें।"
            ),
            "references": [],
        }

    # 2. Build a rich context for the LLM
    context_blocks = []
    references = []
    seen_ids = set()

    for p in similar_pairs:
        ref_id = (getattr(p, "video_id", None), p.timestamp)
        if ref_id in seen_ids:
            continue
        seen_ids.add(ref_id)

        # Build context for LLM
        context_blocks.append(f"Video: {p.video.title}\nTranscript Segment: {p.answer}")

        # Build reference for frontend
        if getattr(p, "video", None):
            ts = p.timestamp or 0
            references.append({
                "video_title": p.video.title,
                "video_id": p.video.youtube_id,
                "timestamp": ts,
                "timestamp_str": format_timestamp(ts),
                "url": build_youtube_url(p.video.url, ts),
                "embed_url": f"https://www.youtube.com/embed/{p.video.youtube_id}?start={ts}",
            })

    full_context = "\n\n---\n\n".join(context_blocks)

    # 3. Generate a broad, detailed answer using the Maharaj's words
    # The prompt now explicitly asks for examples and depth.
    from app.services.llm_service import generate_answer
    answer = generate_answer(query, full_context)

    return {
        "answer": answer,
        "references": references,
        "query": query
    }
