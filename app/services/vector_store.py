# -*- coding: utf-8 -*-
"""
Vector store backed by FAISS with cosine similarity.

Key improvements over the original L2 index:
- Uses IndexFlatIP (inner product) with L2-normalised vectors → true cosine similarity.
- Scores are in [0, 1]; higher = more relevant.
- Results below RAG_THRESHOLD (default 0.40, env-configurable) are filtered out.
- Returned list is sorted by similarity descending and each item carries a .score attribute.
"""
import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from app.database.connection import SessionLocal
from app.models.db_models import QAPair

import json
import logging

logger = logging.getLogger(__name__)

# Configurable similarity threshold (0.0 = accept everything, 1.0 = exact match only)
SIMILARITY_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.40"))

INDEX_PATH = "faiss_index.index"
MAPPING_PATH = "qa_mapping.json"

_model = None
_index = None
_qa_mapping: dict[int, int] = {}  # faiss_position → qa_id


# ---------------------------------------------------------------------------
# Model & index helpers
# ---------------------------------------------------------------------------

def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalise so that inner-product == cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # avoid division by zero
    return vectors / norms


def save_index() -> None:
    global _index, _qa_mapping
    if _index is not None:
        faiss.write_index(_index, INDEX_PATH)
        with open(MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in _qa_mapping.items()}, f)
        logger.info("FAISS index saved to disk (%d items).", _index.ntotal)


def init_index() -> None:
    """
    Load FAISS index from disk, or rebuild from the database if not found.
    Uses IndexFlatIP (cosine similarity via normalised vectors).
    """
    global _index, _qa_mapping
    model = get_embedding_model()
    dimension = model.get_sentence_embedding_dimension()

    if os.path.exists(INDEX_PATH) and os.path.exists(MAPPING_PATH):
        try:
            _index = faiss.read_index(INDEX_PATH)
            with open(MAPPING_PATH, "r", encoding="utf-8") as f:
                _qa_mapping = {int(k): v for k, v in json.load(f).items()}
            logger.info("Loaded FAISS index from disk (%d items).", _index.ntotal)
            return
        except Exception as exc:
            logger.error("Failed to load index from disk: %s. Rebuilding…", exc)

    # Build fresh index (IndexFlatIP for cosine similarity)
    _index = faiss.IndexFlatIP(dimension)
    _qa_mapping = {}

    db = SessionLocal()
    try:
        pairs = db.query(QAPair).all()
        if pairs:
            texts = [p.question + " " + p.answer for p in pairs]
            embeddings = _normalize(model.encode(texts, show_progress_bar=False))
            _index.add(np.array(embeddings, dtype=np.float32))
            for i, p in enumerate(pairs):
                _qa_mapping[i] = p.id
            save_index()
    finally:
        db.close()

    logger.info("Rebuilt FAISS index from database (%d items).", _index.ntotal)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_similar_qa(query: str, top_k: int = 5) -> list:
    """
    Return up to *top_k* QAPair objects sorted by cosine similarity (descending).
    Results below SIMILARITY_THRESHOLD are excluded.
    Each returned object has an extra `.score` attribute (float in [0, 1]).
    """
    global _index, _qa_mapping
    if _index is None:
        init_index()

    if _index.ntotal == 0:
        return []

    model = get_embedding_model()
    query_vec = _normalize(model.encode([query]))

    # Search with a larger candidate set so we have room to filter by threshold
    candidate_k = min(top_k * 3, _index.ntotal)
    scores, indices = _index.search(np.array(query_vec, dtype=np.float32), candidate_k)

    db = SessionLocal()
    results = []
    try:
        from sqlalchemy.orm import joinedload

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx not in _qa_mapping:
                continue
            if float(score) < SIMILARITY_THRESHOLD:
                continue  # below relevance threshold

            qa_id = _qa_mapping[idx]
            qa = (
                db.query(QAPair)
                .options(joinedload(QAPair.video))
                .filter(QAPair.id == qa_id)
                .first()
            )
            if qa is not None:
                qa.score = float(score)  # attach score for downstream ranking
                results.append(qa)

            if len(results) >= top_k:
                break
    finally:
        db.close()

    # Already sorted by FAISS (highest score first for IndexFlatIP)
    return results


# ---------------------------------------------------------------------------
# Index update
# ---------------------------------------------------------------------------

def add_to_index(qa: QAPair) -> None:
    """Add a newly created QA pair to the in-memory index and persist to disk."""
    global _index, _qa_mapping
    if _index is None:
        init_index()

    model = get_embedding_model()
    text = qa.question + " " + qa.answer
    embedding = _normalize(model.encode([text]))
    _index.add(np.array(embedding, dtype=np.float32))
    new_idx = _index.ntotal - 1
    _qa_mapping[new_idx] = qa.id
    save_index()
