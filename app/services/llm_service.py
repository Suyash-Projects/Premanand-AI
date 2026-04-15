import os
import requests
from dotenv import load_dotenv
import logging

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

APIFREE_API_KEY = os.getenv("APIFREE_API_KEY", "")
APIFREE_BASE_URL = os.getenv("APIFREE_BASE_URL", "https://apifreellm.com/api/v1")

logger = logging.getLogger(__name__)

def generate_answer(query: str, context: str) -> str:
    """
    LLM logic priority:
    1. Groq API (Primary - Fastest inference)
    2. OpenRouter API
    3. APIFreeLLM Fallback
    """
    system_prompt = (
        "You are an AI assistant built to answer questions based ONLY on the provided transcripts of Premanand Maharaj.\n"
        "STRICT RULES:\n"
        "1. Answer ONLY from the provided context.\n"
        "2. Answer ALWAYS in pure Hindi, regardless of the input language.\n"
        "3. Keep the tone respectful and spiritual.\n"
        "4. If the answer is not in the context, politely state in Hindi that you don't have the information."
    )
    
    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"
    
    # Try Groq API
    if GROQ_API_KEY:
        try:
            url = f"{GROQ_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama3-8b-8192", # Known working fast groq model
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.5
            }
            res = requests.post(url, headers=headers, json=data, timeout=15)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            else:
                logger.warning(f"Groq failed with {res.status_code}: {res.text}. Falling back.")
        except Exception as e:
            logger.warning(f"Groq exception: {e}. Falling back.")

    # Try OpenRouter with a fallback queue of free models
    if OPENROUTER_API_KEY:
        openrouter_models = [
            "google/gemma-3-27b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/nemotron-nano-9b-v2:free",
            "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
        ]
        
        for model in openrouter_models:
            try:
                url = f"{OPENROUTER_BASE_URL}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Premanand AI",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.5
                }
                res = requests.post(url, headers=headers, json=data, timeout=15)
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
                elif res.status_code == 429:
                    logger.warning(f"OpenRouter {model} rate limited (429). Trying next.")
                else:
                    logger.warning(f"OpenRouter {model} failed with {res.status_code}: {res.text}")
            except Exception as e:
                logger.warning(f"OpenRouter {model} exception: {e}")

    # Try APIFreeLLM
    if APIFREE_API_KEY:
        try:
            url = f"{APIFREE_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {APIFREE_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-3.5-turbo", # Assuming standard endpoint mapping
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.5
            }
            res = requests.post(url, headers=headers, json=data, timeout=15)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"APIFreeLLM failed with {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"APIFreeLLM exception: {e}")
            
    return "क्षमा करें, अभी कोई भी AI सेवा उपलब्ध नहीं है। कृपया थोड़ी देर बाद प्रयास करें।"

import json

def extract_qa_pairs(chunk_text: str) -> list:
    """Uses Groq to extract JSON list of Q&A from a timestamped transcript block."""
    if not GROQ_API_KEY:
        return []
        
    system_prompt = (
        "You are a strict data extractor. Your job is to extract Question and Answer pairs from the provided Hindi transcript. "
        "The transcript contains timestamps in brackets, e.g. [120s]. "
        "Extract any clear spiritual question asked and the spiritual answer given. "
        "Return ONLY a clean JSON array of objects with the keys 'question', 'answer', and 'timestamp' (integer representing the seconds where the answer starts). "
        "If there are no clear questions, return an empty JSON array []."
    )
    
    try:
        url = f"{GROQ_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama3-8b-8192",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Transcript:\n{chunk_text}"}
            ],
            "temperature": 0.3
        }
        res = requests.post(url, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            # remove formatting if wrapped in markdown
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        else:
            logger.error(f"Groq Extraction failed: {res.text}")
    except Exception as e:
        logger.error(f"Groq Extraction exception: {e}")
        
    return []

