"""
backend/llm_key_store.py

Manages customer-provided LLM API keys.
Keys are stored encrypted in a local JSON file (or DB in production).
Priority order when a question comes in:
  1. Customer's own key (if set and valid)
  2. Existing circuit-breaker chain (Qwen → Groq → Gemini)
"""

import os
import json
import base64
import hashlib
import httpx
from typing import Optional
from pathlib import Path

KEY_STORE_PATH = os.getenv("KEY_STORE_PATH", "./data/llm_keys.json")
_SALT = "zecure_llm_salt_v1"   # in production, use a proper secret

SUPPORTED_PROVIDERS = {
    # Model lists current as of July 2026 — several previous defaults here
    # had been deprecated/shut down by their providers:
    #   Groq retired llama-3.3-70b-versatile & mixtral-8x7b-32768 (June 2026)
    #   Google shut down gemini-2.0-flash (June 2026) and the whole 1.5 line
    "openai":    {"name": "OpenAI",           "models": ["gpt-5.5", "gpt-5.4-mini", "gpt-4o-mini"],                "url": "https://api.openai.com/v1/chat/completions"},
    "anthropic": {"name": "Anthropic (Claude)","models": ["claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5-20251001"], "url": "https://api.anthropic.com/v1/messages"},
    "deepseek":  {"name": "DeepSeek",         "models": ["deepseek-v4-flash", "deepseek-v4-pro"],                  "url": "https://api.deepseek.com/chat/completions"},
    "groq":      {"name": "Groq",             "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"], "url": "https://api.groq.com/openai/v1/chat/completions"},
    "gemini":    {"name": "Google Gemini",    "models": ["gemini-3.1-flash-lite", "gemini-3-flash", "gemini-3.1-pro"], "url": "https://generativelanguage.googleapis.com/v1beta/models"},
    "ollama":    {"name": "Ollama (Local)",   "models": ["qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5:3b", "llama3.2"], "url": "http://localhost:11434"},
}


def _simple_encrypt(text: str) -> str:
    """Lightweight obfuscation — NOT production-grade encryption."""
    key = hashlib.sha256(_SALT.encode()).digest()
    data = text.encode()
    encrypted = bytes([data[i] ^ key[i % len(key)] for i in range(len(data))])
    return base64.b64encode(encrypted).decode()


def _simple_decrypt(token: str) -> str:
    key = hashlib.sha256(_SALT.encode()).digest()
    data = base64.b64decode(token.encode())
    return bytes([data[i] ^ key[i % len(key)] for i in range(len(data))]).decode()


def _load_store() -> dict:
    try:
        with open(KEY_STORE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_store(store: dict):
    Path(KEY_STORE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(KEY_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def save_key(provider: str, api_key: str, model: str, customer_id: str = "default") -> dict:
    """Save a customer's API key for a provider."""
    if provider not in SUPPORTED_PROVIDERS:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    store = _load_store()
    if customer_id not in store:
        store[customer_id] = {}
    store[customer_id][provider] = {
        "encrypted_key": _simple_encrypt(api_key),
        "model": model,
        "provider": provider,
        "enabled": True,
    }
    _save_store(store)
    return {"success": True, "provider": provider, "model": model}


def get_key(provider: str, customer_id: str = "default") -> Optional[str]:
    """Retrieve a decrypted API key for a provider."""
    store = _load_store()
    entry = store.get(customer_id, {}).get(provider)
    if not entry or not entry.get("enabled"):
        return None
    try:
        return _simple_decrypt(entry["encrypted_key"])
    except Exception:
        return None


def get_model(provider: str, customer_id: str = "default") -> Optional[str]:
    store = _load_store()
    entry = store.get(customer_id, {}).get(provider)
    return entry.get("model") if entry else None


def get_all_keys(customer_id: str = "default") -> dict:
    """Return all configured providers for a customer (keys masked)."""
    store = _load_store()
    result = {}
    for provider, entry in store.get(customer_id, {}).items():
        key = ""
        try:
            k = _simple_decrypt(entry["encrypted_key"])
            key = k[:6] + "..." + k[-4:] if len(k) > 10 else "****"
        except Exception:
            key = "****"
        result[provider] = {
            "provider": provider,
            "provider_name": SUPPORTED_PROVIDERS.get(provider, {}).get("name", provider),
            "model": entry.get("model", ""),
            "enabled": entry.get("enabled", True),
            "key_preview": key,
        }
    return result


def delete_key(provider: str, customer_id: str = "default") -> dict:
    store = _load_store()
    if customer_id in store and provider in store[customer_id]:
        del store[customer_id][provider]
        _save_store(store)
        return {"success": True}
    return {"success": False, "error": "Key not found"}


def toggle_key(provider: str, enabled: bool, customer_id: str = "default") -> dict:
    store = _load_store()
    if customer_id in store and provider in store[customer_id]:
        store[customer_id][provider]["enabled"] = enabled
        _save_store(store)
        return {"success": True}
    return {"success": False, "error": "Key not found"}


async def validate_key(provider: str, api_key: str, model: str) -> dict:
    """
    Test an API key with a minimal request before saving.
    Returns {"valid": bool, "error": str|None}
    """
    test_prompt = "Reply with the single word: OK"
    try:
        if provider == "openai":
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    SUPPORTED_PROVIDERS["openai"]["url"],
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": test_prompt}], "max_tokens": 5},
                )
                r.raise_for_status()
                return {"valid": True}

        elif provider == "anthropic":
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    SUPPORTED_PROVIDERS["anthropic"]["url"],
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": test_prompt}]},
                )
                r.raise_for_status()
                return {"valid": True}

        elif provider in ("groq", "deepseek"):
            # OpenAI-compatible chat completions endpoint — same request shape as openai
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    SUPPORTED_PROVIDERS[provider]["url"],
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": test_prompt}], "max_tokens": 5},
                )
                r.raise_for_status()
                return {"valid": True}

        elif provider == "gemini":
            url = f"{SUPPORTED_PROVIDERS['gemini']['url']}/{model}:generateContent?key={api_key}"
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(url, json={"contents": [{"parts": [{"text": test_prompt}]}]})
                r.raise_for_status()
                return {"valid": True}

        elif provider == "ollama":
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{SUPPORTED_PROVIDERS['ollama']['url']}/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
                if model not in models:
                    return {"valid": False, "error": f"Model '{model}' not found. Run: ollama pull {model}"}
                return {"valid": True}

    except httpx.HTTPStatusError as e:
        return {"valid": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}

    return {"valid": False, "error": "Unknown provider"}


async def call_customer_llm(prompt: str, customer_id: str = "default", max_tokens: int = 500) -> Optional[tuple[str, str]]:
    """
    Try the customer's own LLM keys in priority order.
    Returns (response_text, model_label) or None if no customer keys configured.
    Priority: openai → anthropic → groq → gemini → ollama
    """
    priority = ["openai", "anthropic", "deepseek", "groq", "gemini", "ollama"]
    store = _load_store()
    customer_keys = store.get(customer_id, {})

    for provider in priority:
        if provider not in customer_keys:
            continue
        entry = customer_keys[provider]
        if not entry.get("enabled"):
            continue
        try:
            key   = _simple_decrypt(entry["encrypted_key"])
            model = entry.get("model", "")
            text  = await _call_provider(provider, key, model, prompt, max_tokens)
            if text:
                return text, f"{SUPPORTED_PROVIDERS[provider]['name']} ({model})"
        except Exception:
            continue
    return None


async def _call_provider(provider: str, api_key: str, model: str, prompt: str, max_tokens: int) -> Optional[str]:
    if provider in ("openai", "groq", "deepseek"):
        # All three use an identical OpenAI-compatible chat completions shape —
        # only the base URL differs (already encoded in SUPPORTED_PROVIDERS).
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                SUPPORTED_PROVIDERS[provider]["url"],
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()

    elif provider == "anthropic":
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                SUPPORTED_PROVIDERS["anthropic"]["url"],
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"].strip()

    elif provider == "gemini":
        url = f"{SUPPORTED_PROVIDERS['gemini']['url']}/{model}:generateContent?key={api_key}"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.1},
            })
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    elif provider == "ollama":
        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(
                f"{SUPPORTED_PROVIDERS['ollama']['url']}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": max_tokens, "temperature": 0.1}},
            )
            r.raise_for_status()
            return r.json()["response"].strip()

    return None
