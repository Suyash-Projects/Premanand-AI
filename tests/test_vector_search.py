# -*- coding: utf-8 -*-
"""
Unit tests for the vector store / FAISS search layer.

These tests operate against the real on-disk FAISS index (if present)
and also verify behaviour when the index is empty or missing.
"""
import os
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

os.environ["PYTHONUTF8"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./bhaktimarg_qa.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_vector_store():
    """Reset module-level globals so each test starts clean."""
    import app.services.vector_store as vs
    vs._index = None
    vs._model = None
    vs._qa_mapping = {}


# ---------------------------------------------------------------------------
# Threshold filtering
# ---------------------------------------------------------------------------

def test_search_returns_list(tmp_path, monkeypatch):
    """search_similar_qa must always return a list (never None)."""
    import app.services.vector_store as vs
    _reset_vector_store()

    # Point index files somewhere that doesn't exist so it rebuilds from DB
    monkeypatch.setattr(vs, "INDEX_PATH", str(tmp_path / "test.index"))
    monkeypatch.setattr(vs, "MAPPING_PATH", str(tmp_path / "test_map.json"))

    result = vs.search_similar_qa("भक्ति क्या है?", top_k=3)
    assert isinstance(result, list)


def test_search_returns_empty_when_index_is_empty():
    """If the index has 0 vectors, search should return an empty list immediately."""
    import app.services.vector_store as vs
    import faiss

    _reset_vector_store()
    model = vs.get_embedding_model()
    dim = model.get_sentence_embedding_dimension()

    # Inject a fresh empty index
    vs._index = faiss.IndexFlatIP(dim)
    vs._qa_mapping = {}

    result = vs.search_similar_qa("कोई भी सवाल", top_k=5)
    assert result == []


def test_low_similarity_results_filtered_out():
    """
    Results below SIMILARITY_THRESHOLD should not appear.
    We patch _index.search to return a score of 0.01 (well below threshold).
    """
    import app.services.vector_store as vs
    import faiss

    _reset_vector_store()
    model = vs.get_embedding_model()
    dim = model.get_sentence_embedding_dimension()

    # Build a tiny index with one fake vector
    fake_vec = np.random.randn(1, dim).astype(np.float32)
    # Normalise
    fake_vec /= np.linalg.norm(fake_vec, axis=1, keepdims=True)

    vs._index = faiss.IndexFlatIP(dim)
    vs._index.add(fake_vec)
    vs._qa_mapping = {0: 9999}  # points to a non-existent QA id

    # Force a very low score by patching search
    with patch.object(vs._index, "search", return_value=(
        np.array([[0.01]], dtype=np.float32),  # score below threshold
        np.array([[0]], dtype=np.int64),
    )):
        result = vs.search_similar_qa("test", top_k=3)

    assert result == [], "Results below similarity threshold should be filtered out"


# ---------------------------------------------------------------------------
# Real index tests (skipped if FAISS file doesn't exist on disk)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists("faiss_index.index"),
    reason="FAISS index file not found on disk – run ingest first",
)
def test_real_index_returns_results_for_hindi_query():
    """With the real index, a known Hindi spiritual query should return ≥1 result."""
    import app.services.vector_store as vs
    _reset_vector_store()

    results = vs.search_similar_qa("भक्ति का अर्थ क्या है?", top_k=3)
    assert len(results) >= 1, "Expected at least one relevant result from the real index"


@pytest.mark.skipif(
    not os.path.exists("faiss_index.index"),
    reason="FAISS index file not found on disk – run ingest first",
)
def test_real_index_results_have_score_attribute():
    """Results from the real index should carry a .score float attribute."""
    import app.services.vector_store as vs
    _reset_vector_store()

    results = vs.search_similar_qa("राधे राधे", top_k=3)
    for r in results:
        assert hasattr(r, "score"), "Each result should have a .score attribute"
        # Cosine similarity via IndexFlatIP on L2-normalised vectors is in [0,1]
        # but float32 normalisation can push it marginally above 1.0
        assert r.score >= 0.0, f"Negative score is invalid: {r.score}"


@pytest.mark.skipif(
    not os.path.exists("faiss_index.index"),
    reason="FAISS index file not found on disk – run ingest first",
)
def test_real_index_scores_are_sorted_descending():
    """Results should be ordered highest-similarity-first."""
    import app.services.vector_store as vs
    _reset_vector_store()

    results = vs.search_similar_qa("कृष्ण भक्ति", top_k=5)
    scores = [r.score for r in results]
    # Allow for float32 ties within a small epsilon
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1] - 1e-5, (
            f"Scores not in descending order: {scores[i]} < {scores[i+1]}"
        )
