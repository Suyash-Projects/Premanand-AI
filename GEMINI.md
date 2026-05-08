# Bhakti Marg AI - Project Instructions 🕉

This document serves as the primary technical guide for the Premanand AI repository. Adhere to these mandates to maintain architectural integrity and consistency.

---

## 🏗 Architecture & Stack

- **Framework**: FastAPI (Python 3.11+)
- **Database**: SQLAlchemy with SQLite (`bhaktimarg_qa.db`).
- **Vector Store**: FAISS (using `IndexFlatIP` for cosine similarity).
- **Embeddings**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- **LLM Strategy**: Groq (primary) -> OpenRouter -> APIFreeLLM (failover).
- **Frontend**: Single-page application using Tailwind CSS and Vanilla JS.

---

## 🛠 Core Workflows

### 1. Data Ingestion (ETL)
- **Bulk Ingestion**: Use `fetch_and_ingest.py`. It handles parallel fetching, rate-limiting (YouTube transcript bans), and incremental updates.
- **Background Updates**: Triggered via `POST /api/process-channel`. Uses `BackgroundTasks` to avoid blocking the API.
- **Extraction**: LLM extracts structured Q&A pairs from transcript chunks. Always include timestamps.

### 2. RAG Pipeline
- **Retrieval**: `search_similar_qa` filters by `RAG_THRESHOLD` (default: 0.40).
- **Deduplication**: Context blocks are deduplicated by `(video_id, timestamp)` before being sent to the LLM.
- **Prompting**: The system prompt strictly enforces Hindi responses and grounding in the provided context.

---

## 📝 Coding Standards & Conventions

- **Encoding**: Always use UTF-8. Force it in Windows environments using `os.environ["PYTHONUTF8"] = "1"`.
- **Environment**: Use `.env` for all keys. Never hardcode credentials.
- **Type Safety**: Use Pydantic models for API request/response validation.
- **Error Handling**: 
    - API endpoints should return clear 4xx/5xx status codes.
    - The LLM service should handle timeouts and failover gracefully.
- **Database**:
    - Do NOT commit `.db` or `.index` files.
    - If the FAISS index is missing, it must auto-rebuild from the SQLite database on startup.

---

## 🧪 Testing

- **Framework**: `pytest`.
- **Execution**: Run via `python -m pytest tests/ -v`.
- **Mocking**: Always mock LLM calls in `conftest.py` to keep tests fast and offline-capable.
- **Coverage**: Every new API endpoint or service logic change must be accompanied by a test case in `tests/`.

---

## 🚀 Deployment

- **Procfile**: Maintained for Railway/Render/Heroku compatibility.
- **Port Detection**: `run.py` includes a dynamic port scanner to avoid local conflicts.
- **Static Files**: Mounted at `/static`. Do not use external CDNs for core application logic.
