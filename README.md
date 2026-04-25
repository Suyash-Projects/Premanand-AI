# Bhakti Marg AI 🕉

AI-powered spiritual Q&A assistant trained on the teachings of **Shri Hit Premanand Govind Sharan Ji Maharaj**. Ask questions in Hindi or English and receive answers grounded in available video transcripts, with timestamped YouTube references.

---

## Quick Start

### Prerequisites
- Python 3.11+ on PATH
- API key for at least one LLM provider (Groq recommended — free, fast)

### Setup

```powershell
# 1. Clone the repo
git clone <your-repo-url>
cd "Premanand AI"

# 2. Create & activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env and fill in your API keys (GROQ_API_KEY is the minimum needed)

# 5. Start the server
python run.py
```

The server auto-detects a free port starting at 8000. Open `http://localhost:8000` in your browser.

---

## Running Tests

```powershell
pip install pytest httpx pytest-asyncio   # one-time, already in requirements.lock
pytest tests/ -v
```

All tests run offline — no live LLM or network calls required.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | Groq API key (fastest, recommended) | ✅ At least one LLM |
| `OPENROUTER_API_KEY` | OpenRouter API key (free models available) | Optional |
| `APIFREE_API_KEY` | APIFreeLLM key | Optional |
| `DATABASE_URL` | SQLite path (default: `sqlite:///./bhaktimarg_qa.db`) | Auto |
| `RAG_THRESHOLD` | Similarity threshold 0–1 (default: `0.40`) | Optional |
| `APP_PORT` | Override server port (default: auto-detect from 8000) | Optional |
| `PYTHONUTF8` | Force UTF-8 on Windows (set to `1`) | Recommended on Windows |

---

## Architecture

```
User Query
    │
    ▼
FAISS Vector Search (cosine similarity)
    │  paraphrase-multilingual-MiniLM-L12-v2 embeddings
    │  IndexFlatIP + L2-normalised vectors
    │  Similarity threshold: 0.40 (configurable)
    ▼
RAG Pipeline
    │  Deduplicates by (video_id, timestamp)
    │  Caps context at 4,000 chars
    │  Ranks references by similarity score
    ▼
LLM (Groq → OpenRouter → APIFreeLLM)
    │  Hindi-enforced system prompt
    ▼
Answer + Timestamped YouTube References
```

**Data**: 64 Satsang videos · 224 Q&A pairs extracted by Groq LLaMA 3.1

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ask` | Answer a spiritual question |
| `GET` | `/api/videos` | List all indexed videos |
| `GET` | `/api/qa` | List all Q&A pairs |
| `POST` | `/api/demo` | Load demo status (for UI button) |
| `POST` | `/api/process-channel` | Trigger channel re-ingestion |
| `GET` | `/api/admin/stats` | DB + index stats |
| `GET` | `/api/admin/health` | LLM provider availability |

---

## Deployment

### Railway / Render / Heroku
The `Procfile` handles the start command automatically:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
Set your environment variables in the platform dashboard.

---

## Windows UTF-8 Note

If you see garbled Hindi text (like `à¤...`) in your console, add this to your `.env`:
```
PYTHONUTF8=1
```
Or run PowerShell with `$env:PYTHONUTF8=1` before starting the server.

---

## Security

- **Never commit `cookies.txt`** — it is listed in `.gitignore`
- **Never commit `.env`** — use `.env.example` as the template
- The database (`.db` files) and FAISS index are also gitignored

---

## License

For educational and spiritual use. All teachings belong to Shri Hit Premanand Govind Sharan Ji Maharaj.
