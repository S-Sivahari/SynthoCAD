"""Gemini LLM Service - Low-level API calls to Google Generative Language API.

This module provides the raw LLM call functionality.
JSON parsing and prompt building is handled by the main pipeline (core/main.py).
"""
import os
import time
import requests
from typing import Optional

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _extract_text_from_response(resp_json: dict) -> str:
    """Extract text from Gemini API response in generateContent format."""
    if not resp_json:
        return ""
    
    # v1beta format: candidates[0].content.parts[0].text
    if "candidates" in resp_json and resp_json["candidates"]:
        first = resp_json["candidates"][0]
        if isinstance(first, dict):
            if "content" in first and isinstance(first["content"], dict):
                content = first["content"]
                if "parts" in content and content["parts"]:
                    part = content["parts"][0]
                    if isinstance(part, dict) and "text" in part:
                        return part["text"]
            if "text" in first:
                return first["text"]
    
    return str(resp_json)


def call_gemini(prompt: str, model: Optional[str] = None, max_tokens: int = 2048, temperature: float = 0.1) -> str:
    """Call the Google Generative Language (Gemini) REST endpoint.
    
    Args:
        prompt: The full prompt text to send
        model: Model name (default from GEMINI_MODEL env var or gemini-2.0-flash)
        max_tokens: Maximum output tokens
        temperature: Sampling temperature (0.0-1.0)
    
    Returns:
        Raw text response from the model
        
    Raises:
        RuntimeError: If API key not set or request fails after retries
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")

    if model is None:
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    url = f"{BASE_URL}/models/{model}:generateContent"

    body = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_tokens),
        }
    }

    # Retry logic for rate limits
    max_retries = 3
    for attempt in range(max_retries):
        resp = requests.post(url, params={"key": api_key}, json=body, timeout=120)
        
        if resp.status_code == 429:
            wait_time = (attempt + 1) * 10
            print(f"  Rate limited. Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            continue
        
        resp.raise_for_status()
        data = resp.json()
        return _extract_text_from_response(data)
    
    raise RuntimeError(f"Failed after {max_retries} retries due to rate limiting")
