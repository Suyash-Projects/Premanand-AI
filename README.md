# Bhakti Marg AI 🕉

AI-powered spiritual Q&A assistant trained on the teachings of **Shri Hit Premanand Govind Sharan Ji Maharaj**. Ask questions in Hindi or English and receive answers grounded in available video transcripts, with timestamped YouTube references.

---

## 🚀 Functionality

- **Semantic Q&A**: Asks spiritual questions and receives answers strictly grounded in Maharaj Ji's teachings.
- **Timestamped References**: Every answer comes with direct links to the exact moment in the YouTube video where the topic was discussed.
- **Multilingual Support**: Supports queries in Hindi and English (uses a multilingual embedding model).
- **Automated Ingestion**: Background tasks and scripts to fetch latest videos from the "Bhajan Marg" channel, extract Q&A pairs via LLM, and update the vector index automatically.
- **Professional UI**: Modern, responsive dashboard built with Tailwind CSS and FastAPI.

---

## 🛠 Quick Start

### Prerequisites
- Python 3.11+
- API key for at least one LLM provider (Groq recommended)

### Setup

```powershell
# 1. Clone the repo
git clone <your-repo-url>
cd "Premanand AI"

# 2. Create & activate a virtual environment
# Note: If you have an existing 'venv', it's recommended to recreate it
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

## 📊 Data Pipeline (End-to-End)

The project includes a robust pipeline to go from raw YouTube videos to a searchable AI:

1. **Standalone Bulk Ingestion**:
   Run `python fetch_and_ingest.py` to fetch videos from the channel, download transcripts, and extract Q&A pairs in bulk. It handles retries, rate-limiting, and state management.
   
2. **Background Updates**:
   Use the `/api/process-channel` endpoint to trigger a background task that scans for new videos and updates the database while the app is running.

3. **Vector Index**:
   The app uses FAISS (Facebook AI Similarity Search) with `paraphrase-multilingual-MiniLM-L12-v2` embeddings for high-speed, relevant retrieval.

---

## 🧪 Running Tests

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
