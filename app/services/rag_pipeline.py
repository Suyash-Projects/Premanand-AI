from app.services.vector_store import search_similar_qa
from app.services.llm_service import generate_answer
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
    # 1. Embed query and search
    similar_pairs = search_similar_qa(query, top_k=5)
    
    if not similar_pairs:
        return {
            "answer": "क्षमा करें, मुझे इस प्रश्न का उत्तर मेरे पास उपलब्ध सामग्री में नहीं मिला। पूर्ण सत्य जानने के लिए कृपया महाराज जी के प्रवचन सुनें।",
            "references": []
        }

    # 2. Build context and collect references
    context_lines = []
    references = []
    seen_videos = set()

    for p in similar_pairs:
        context_lines.append(f"Q: {p.question}\nA: {p.answer}")
        
        if getattr(p, 'video', None) and p.video.youtube_id not in seen_videos:
            seen_videos.add(p.video.youtube_id)
            ts = p.timestamp or 0
            ref_url = build_youtube_url(p.video.url, ts)
            references.append({
                "video_title": p.video.title,
                "video_id": p.video.youtube_id,
                "timestamp": ts,
                "timestamp_str": format_timestamp(ts),
                "url": ref_url,
                "embed_url": f"https://www.youtube.com/embed/{p.video.youtube_id}?start={ts}"
            })

    context = "\n---\n".join(context_lines)
    
    # 3. Request LLM Answer (Hindi enforced in system prompt)
    answer = generate_answer(query, context)
        
    return {
        "answer": answer,
        "references": references,
        # keep old key for backward compat
        "reference": references[0] if references else None
    }
