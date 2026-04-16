# ॐ Bhakti Marg AI

A production-ready, spiritual Q&A system that leverages Retrieval-Augmented Generation (RAG) to provide profound answers based strictly on the teachings and transcripts of **Premanand Maharaj**.

![Bhakti Marg AI UI](https://img.shields.io/badge/Tech-FastAPI%20+%20FAISS%20+%20LLM-orange)

## 🚀 Features
- **Hindi-Only Responses**: The AI strictly responds in Hindi, maintaining the spiritual essence of the original teachings.
- **Transcript Deep-Linking**: Every answer comes with a direct reference to the specific YouTube video and timestamp.
- **Automated Extraction Pipeline**: Built-in scraper using `yt-dlp` and `youtube-transcript-api` to pull data from the `@BhajanMarg` channel.
- **Multi-LLM Resilience**: intelligent fallback logic across **Groq (Primary)**, **OpenRouter**, and **APIFreeLLM**.
- **Vector Search**: High-performance semantic retrieval using `faiss-cpu` and a multilingual embedding model.

---

## 🛠️ Prerequisites
- **Python 3.11+**
- **Virtual Environment** (recommended)
- **API Keys**: You will need keys for at least one of the following:
  - [Groq AI](https://console.groq.com/) (Highly Recommended for speed)
  - [OpenRouter](https://openrouter.ai/)
  - [RapidAPI](https://rapidapi.com/)

---

## ⚙️ Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/Suyash-Projects/Premanand-AI.git
cd Premanand-AI
```

### 2. Create and Activate Virtual Environment
**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a file named `.env` in the root directory and paste your keys:
```env
# AI API Keys
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key

# Database
DATABASE_URL=sqlite:///./bhaktimarg_qa.db
SECRET_KEY=generate_a_random_string_here
```

---

## 🏃 Running the Application

Launch the server using the dynamic port wrapper:
```bash
python run.py
```
- The application will automatically find an available port starting from `8000`.
- Open your browser to `http://localhost:8000` (or the port displayed in terminal).

---

## 📊 Data Extraction (Scraping)

To populate your database with real teachings from the Bhajan Marg channel:

1. **Trigger Background Scraper**:
   Send a POST request to the `/api/process-channel` endpoint. You can do this via terminal:
   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/process-channel?max_videos=10"
   ```
2. **Watch Progress**:
   Open the file `extraction_progress.txt` in your editor to see real-time updates as the AI extracts Q&A pairs.

---

## 🏗️ Tech Stack
- **Backend**: FastAPI (Python)
- **Database**: SQLAlchemy + SQLite
- **Vector Engine**: FAISS (Facebook AI Similarity Search)
- **Embeddings**: `sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2)
- **Frontend**: Vanilla JS + Tailwind CSS + Lucide Icons

---

## 🙏 Credits
- **Teachings**: Shri Hit Premanand Govind Sharan Ji Maharaj.
- **Channel**: [Bhajan Marg](https://www.youtube.com/@BhajanMarg).

---
*Radhe Radhe!*
