from app.services.vector_store import search_similar_qa
from app.services.llm_service import generate_answer
import logging

logger = logging.getLogger(__name__)

def process_query(query: str) -> dict:
    # 1. Embed query and search
    similar_pairs = search_similar_qa(query, top_k=3)
    
    if not similar_pairs:
        return {
            "answer": "क्षमा करें, मुझे इस प्रश्न का उत्तर मेरे पास उपलब्ध सामग्री में नहीं मिला। पूर्ण सत्य जानने के लिए कृपया महाराज जी के प्रवचन सुनें।",
            "reference": None
        }

    # 2. Build context
    context_lines = []
    best_reference = None
    for p in similar_pairs:
        context_lines.append(f"Q: {p.question}\nA: {p.answer}")
        if not best_reference and getattr(p, 'video', None):
            best_reference = {
                "video_url": p.video.url,
                "timestamp": p.timestamp
            }

    context = "\n---\n".join(context_lines)
    
    # 3. Request LLM Answer
    # We enforce Hindi inside system prompt in llm_service.
    answer = generate_answer(query, context)
        
    return {
        "answer": answer,
        "reference": best_reference
    }
