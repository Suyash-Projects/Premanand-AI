# -*- coding: utf-8 -*-
"""
Real automated tests for FastAPI endpoints.

Tests covered:
  - GET  /api/videos              → 200, list response
  - GET  /api/admin/stats         → 200, expected keys
  - GET  /api/admin/health        → 200, expected keys
  - POST /api/demo                → 200, status == "success"
  - POST /api/ask  (empty query)  → 400, validation error
  - POST /api/ask  (valid query)  → 200, "answer" key present
  - POST /api/ask  (no DB hits)   → 200, Hindi fallback answer
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# /api/videos
# ---------------------------------------------------------------------------

def test_get_videos_returns_list(client):
    """GET /api/videos should return HTTP 200 with a JSON list."""
    resp = client.get("/api/videos")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list), "Expected a JSON array"


def test_get_videos_schema(client):
    """Each video in the list must have id, title, youtube_id, url fields."""
    resp = client.get("/api/videos")
    videos = resp.json()
    if videos:  # Only validate schema if there is at least one record
        v = videos[0]
        assert "id" in v
        assert "title" in v
        assert "youtube_id" in v
        assert "url" in v


# ---------------------------------------------------------------------------
# /api/admin/stats
# ---------------------------------------------------------------------------

def test_admin_stats_keys(client):
    """GET /api/admin/stats should return videos, qa_pairs, and index_size."""
    resp = client.get("/api/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "videos" in data
    assert "qa_pairs" in data
    assert "index_size" in data
    assert isinstance(data["videos"], int)
    assert isinstance(data["qa_pairs"], int)


def test_admin_stats_counts_are_positive(client):
    """The pre-populated DB should have at least 1 video and 1 Q&A pair."""
    resp = client.get("/api/admin/stats")
    data = resp.json()
    assert data["videos"] >= 1, "Expected at least one video in the database"
    assert data["qa_pairs"] >= 1, "Expected at least one Q&A pair in the database"


# ---------------------------------------------------------------------------
# /api/admin/health
# ---------------------------------------------------------------------------

def test_admin_health_keys(client):
    """GET /api/admin/health should return status, groq, openrouter, apifree keys."""
    resp = client.get("/api/admin/health")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("status", "groq", "openrouter", "apifree"):
        assert key in data, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# /api/demo
# ---------------------------------------------------------------------------

def test_demo_endpoint_success(client):
    """POST /api/demo should return status == 'success'."""
    resp = client.post("/api/demo")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "success"
    assert "videos" in data
    assert "qa_pairs" in data


# ---------------------------------------------------------------------------
# /api/ask – validation
# ---------------------------------------------------------------------------

def test_ask_empty_query_returns_400(client):
    """POST /api/ask with an empty query string must return HTTP 400."""
    resp = client.post("/api/ask", json={"query": ""})
    assert resp.status_code == 400


def test_ask_whitespace_only_returns_400(client):
    """POST /api/ask with only whitespace must also return HTTP 400."""
    resp = client.post("/api/ask", json={"query": "   "})
    assert resp.status_code == 400


def test_ask_missing_query_field_returns_422(client):
    """POST /api/ask with no query field returns Pydantic validation error (422)."""
    resp = client.post("/api/ask", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/ask – valid query (LLM patched in conftest)
# ---------------------------------------------------------------------------

def test_ask_valid_query_returns_answer(client):
    """POST /api/ask with a real Hindi question should return 200 + answer key."""
    resp = client.post("/api/ask", json={"query": "भक्ति क्या है?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data, "Response must contain 'answer' key"
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0


def test_ask_response_has_references_key(client):
    """The /api/ask response should always include a 'references' list."""
    resp = client.post("/api/ask", json={"query": "प्रेम क्या है?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "references" in data
    assert isinstance(data["references"], list)


def test_ask_no_results_returns_hindi_fallback(client):
    """When vector search returns no results, the response should use the Hindi fallback."""
    with patch("app.services.rag_pipeline.search_similar_qa", return_value=[]):
        resp = client.post("/api/ask", json={"query": "xyzzy nonsense gibberish"})
    assert resp.status_code == 200
    data = resp.json()
    # Fallback answer contains Hindi text (specifically 'क्षमा')
    assert "क्षमा" in data["answer"], (
        "Expected the Hindi fallback message when no results are found"
    )
    assert data["references"] == []
