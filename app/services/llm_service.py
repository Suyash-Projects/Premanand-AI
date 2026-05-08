# -*- coding: utf-8 -*-
import os
import requests
from dotenv import load_dotenv
import logging
import json
import time

load_dotenv()

# NVIDIA NIM (NVIDIA Build) - Best High-Quality Model
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
    LLM logic priority:
    1. NVIDIA (Best - Llama 3.1 405B)
    2. NVIDIA (High Quality - Llama 3.1 70B)
    3. Groq (Fast - Llama 3.1 70B)
    4. OpenRouter (Free Fallbacks)
    5. APIFreeLLM (Last resort)
    """
    system_prompt = (
        "You are an AI assistant built to answer spiritual questions based ONLY on the provided transcripts of Shri Hit Premanand Govind Sharan Ji Maharaj.\n"
        "GOAL: Provide a BROAD, COMPREHENSIVE, and DETAILED answer.\n"
        "STRICT RULES:\n"
        "1. GROUNDING: Answer ONLY using the provided transcript segments. If multiple segments talk about the same topic, combine them for a fuller answer.\n"
        "2. EXAMPLES: Always include any parables, stories, or specific examples given by Maharaj ji in the transcripts to illustrate the points.\n"
        "3. DEPTH: Do not just give a summary. Explain the 'why' and 'how' of the spiritual practice or concept as explained by Maharaj ji.\n"
        "4. LANGUAGE: Answer ALWAYS in pure, respectful Hindi (साधु भाषा).\n"
        "5. NO HALLUCINATION: If the provided context doesn't contain the answer or an example, do not invent one."
    )
    
    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"
    
    # 1 & 2. Try NVIDIA Models (Best and High Quality)
    if NVIDIA_API_KEY:
        nvidia_models = ["meta/llama-3.1-405b-instruct", "meta/llama-3.1-70b-instruct"]
        for model in nvidia_models:
            try:
                url = f"{NVIDIA_BASE_URL}/chat/completions"
                headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
                data = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.5,
                    "max_tokens": 1024
                }
                # Increased timeout to 60s for massive models
                res = requests.post(url, headers=headers, json=data, timeout=60)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
                logger.warning(f"NVIDIA {model} failed ({res.status_code}). Trying next.")
            except Exception as e:
                logger.warning(f"NVIDIA {model} error: {str(e)[:100]}")

    # 3. Try Groq API
    if GROQ_API_KEY:
        try:
            url = f"{GROQ_BASE_URL}/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            data = {
                "model": "llama-3.1-70b-versatile",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.5
            }
            res = requests.post(url, headers=headers, json=data, timeout=20)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Groq error: {str(e)[:100]}")

    # 4. Try OpenRouter (Free models)
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

    # 5. Last Resort
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
        res = requests.post(provider["url"], headers=headers, json=data, timeout=20) # Fail fast
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            content = content.replace("```json", "").replace("```", "").strip()
            if "[" in content and "]" in content:
                content = content[content.find("["):content.rfind("]")+1]
            
            pairs = json.loads(content)
            # Sanitize timestamps to ensure they are integers
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
    """
    Extraction Priority (Speed > Quality):
    Runs the fastest available models concurrently. The first one to return a valid JSON list wins.
    """
    import concurrent.futures
    
    system_prompt = (
        "You are a strict data extractor. Your task is to extract clear Question and Answer pairs from the provided Hindi transcript. "
        "Each pair must represent a distinct spiritual query and its resolution. "
        "Return ONLY a clean JSON array of objects with the keys 'question', 'answer', and 'timestamp'. "
        "If no distinct questions are found, return []."
    )
    
    providers = []
    
    # Fast models only for extraction (No 405B)
    if GROQ_API_KEY:
        # Groq 70B is usually the absolute fastest
        providers.append({"url": f"{GROQ_BASE_URL}/chat/completions", "key": GROQ_API_KEY, "model": "llama-3.1-70b-versatile"})
        # Groq 8B as backup
        providers.append({"url": f"{GROQ_BASE_URL}/chat/completions", "key": GROQ_API_KEY, "model": "llama-3.1-8b-instant"})
    
    if NVIDIA_API_KEY:
        # NVIDIA 70B is very fast and high quality
        providers.append({"url": f"{NVIDIA_BASE_URL}/chat/completions", "key": NVIDIA_API_KEY, "model": "meta/llama-3.1-70b-instruct"})
        
    if not providers:
        return []

    # Run extraction concurrently across platforms. First to finish wins.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {executor.submit(_call_provider, p, system_prompt, chunk_text): p for p in providers}
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                return result
                
    return []


