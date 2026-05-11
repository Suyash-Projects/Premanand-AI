# -*- coding: utf-8 -*-
import os
import requests
from dotenv import load_dotenv
import logging
import json
import time

load_dotenv()

# NVIDIA NIM (NVIDIA Build)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Groq - Fastest inference
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# OpenRouter - Multi-provider fallback
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# APIFreeLLM - Last resort
APIFREE_API_KEY = os.getenv("APIFREE_API_KEY", "")
APIFREE_BASE_URL = os.getenv("APIFREE_BASE_URL", "https://apifreellm.com/api/v1")

logger = logging.getLogger(__name__)


def generate_answer(query: str, context: str) -> str:
    """
    LLM logic priority (optimized for speed):
    1. Groq (Fastest - Llama 3.1 70B) - Primary choice
    2. OpenRouter (Free Fallbacks)
    3. NVIDIA (if configured and working)
    """
    system_prompt = (
        "You are an AI assistant built to answer spiritual questions based ONLY on the provided transcripts of Shri Hit Premanand Govind Sharan Ji Maharaj.\n"
        "OUTPUT FORMAT (CRITICAL - Follow strictly):\n"
        "1. Start with a brief SUMMARY of what Maharaj ji teaches about this topic.\n"
        "2. Use **bold** for key spiritual concepts and important terms.\n"
        "3. Use bullet points (•) for distinct teachings.\n"
        "4. Include SPECIFIC EXAMPLES and stories from the transcripts.\n"
        "5. If multiple transcripts discuss the same topic, combine them for a COMPLETE answer.\n"
        "6. Answer in pure Hindi (साधु भाषा).\n"
        "7. NEVER invent or hallucinate - only use information from provided context.\n"
        "\n"
        "Example structure:\n"
        "**सारांश:** [Brief summary of Maharaj ji's teachings on this topic]\n\n"
        "**मुख्य बिंदु:**\n"
        "• [Point 1 with example from transcript]\n"
        "• [Point 2 with example from transcript]\n\n"
        "**उदाहरण:** [Specific story or parable from the videos]\n"
    )

    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

    # 1. Try Groq FIRST (fastest, most reliable) - use 8B for speed, 70B for quality
    if GROQ_API_KEY:
        # Try 8B first (faster), then 70B if needed
        models = ["llama-3.1-8b-instant", "llama-3.1-70b-versatile"]
        for model in models:
            try:
                url = f"{GROQ_BASE_URL}/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                data = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.5,
                    "max_tokens": 512
                }
                res = requests.post(url, headers=headers, json=data, timeout=10)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
                logger.warning(f"Groq {model} failed ({res.status_code})")
            except Exception as e:
                logger.warning(f"Groq {model} error: {str(e)[:80]}")

    # 2. Try OpenRouter (free models)
    if OPENROUTER_API_KEY:
        for model in ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-2-27b-it:free"]:
            try:
                url = f"{OPENROUTER_BASE_URL}/chat/completions"
                headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                data = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.5
                }
                res = requests.post(url, headers=headers, json=data, timeout=20)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"OpenRouter {model} error: {str(e)[:100]}")

    # 3. Try NVIDIA (lower priority)
    if NVIDIA_API_KEY:
        try:
            url = f"{NVIDIA_BASE_URL}/chat/completions"
            headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
            data = {
                "model": "meta/llama-3.1-70b-instruct",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.5,
                "max_tokens": 512
            }
            res = requests.post(url, headers=headers, json=data, timeout=10)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            logger.warning(f"NVIDIA failed ({res.status_code})")
        except Exception as e:
            logger.warning(f"NVIDIA error: {str(e)[:100]}")

    # 4. Last Resort
    return "क्षमा करें, अभी कोई भी AI सेवा उपलब्ध नहीं है।"


def _call_provider(provider: dict, system_prompt: str, chunk_text: str) -> list:
    """Helper to make a single API call for extraction with a fast timeout."""
    try:
        headers = {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"}
        data = {
            "model": provider["model"],
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Transcript:\n{chunk_text}"}],
            "temperature": 0.1
        }
        res = requests.post(provider["url"], headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            content = content.replace("```json", "").replace("```", "").strip()
            if "[" in content and "]" in content:
                content = content[content.find("["):content.rfind("]")+1]

            pairs = json.loads(content)
            for p in pairs:
                ts = p.get("timestamp", 0)
                if isinstance(ts, str):
                    ts = "".join(filter(str.isdigit, ts))
                    p["timestamp"] = int(ts) if ts else 0
                elif not isinstance(ts, (int, float)):
                    p["timestamp"] = 0
            return pairs
        return None
    except Exception:
        return None


def extract_qa_pairs(chunk_text: str) -> list:
    """Extract QA pairs from transcript using fastest available model."""
    import concurrent.futures

    system_prompt = (
        "Extract Question and Answer pairs from Hindi transcript. "
        "Return ONLY a clean JSON array with keys 'question', 'answer', 'timestamp'. "
        "If no pairs found, return []."
    )

    providers = []

    if GROQ_API_KEY:
        providers.append({"url": f"{GROQ_BASE_URL}/chat/completions", "key": GROQ_API_KEY, "model": "llama-3.1-70b-versatile"})

    if NVIDIA_API_KEY:
        providers.append({"url": f"{NVIDIA_BASE_URL}/chat/completions", "key": NVIDIA_API_KEY, "model": "meta/llama-3.1-70b-instruct"})

    if not providers:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {executor.submit(_call_provider, p, system_prompt, chunk_text): p for p in providers}

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                return result

    return []