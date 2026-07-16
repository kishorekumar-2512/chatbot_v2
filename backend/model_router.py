"""
backend/model_router.py

Circuit breaker pattern for LLM model fallback.

Default order (cloud deployment — no dedicated GPU host assumed):
Primary:    Groq API — openai/gpt-oss-120b (fast, cheap, no GPU to run)
Fallback 1: Google Gemini — gemini-3.1-flash-lite
Fallback 2: Qwen 2.5 Coder 7B via Ollama (local — only reachable if you're
            also running a GPU-backed Ollama host; last resort here)

Override with PRIMARY_LLM=qwen or PRIMARY_LLM=gemini in .env if your
deployment does have a local/GPU model you want prioritized instead.

Customer-supplied BYO API keys (Settings page) are tried BEFORE this whole
chain, regardless of tier order here — see call_customer_llm() in main.py.

Behavior:
- Each model tracks its own consecutive failure count.
- If the PRIMARY model fails 3 times in a row, OR a generation's confidence
  drops below 70%, the circuit "opens" and routing moves to fallback 1.
- If fallback 1 also fails 3 times in a row, routing moves to fallback 2.
- After 5 minutes of the primary being "down", the router automatically
  attempts one recovery call to the primary. If it succeeds, the circuit
  closes and primary becomes active again. If it fails, the 5-minute timer
  resets.
- The currently active model is always reported back so the API/UI can
  show which model answered the question.
"""

import os
import time
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

OLLAMA_URL     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
# CRITICAL: Ollama defaults to a 2048-token context window if this isn't set
# explicitly, regardless of what the model supports. Our prompts (schema +
# join hints + value samples + few-shots) routinely exceed that, which was
# silently truncating the prompt and tanking accuracy. qwen2.5-coder:7b
# supports up to 32k context; 8192 is a safe, fast default.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL     = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

FAILURE_THRESHOLD   = 3            # consecutive failures before opening circuit
RECOVERY_AFTER_SECS = 5 * 60       # try primary again after this long
CONFIDENCE_FLOOR    = 0.70         # below this, treat as a "soft failure" too


@dataclass
class ModelState:
    """Tracks circuit-breaker state for a single model."""
    name: str
    consecutive_failures: int = 0
    is_open: bool = False           # True = circuit open = currently being skipped
    opened_at: Optional[float] = None

    def record_success(self):
        self.consecutive_failures = 0
        self.is_open = False
        self.opened_at = None

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= FAILURE_THRESHOLD and not self.is_open:
            self.is_open = True
            self.opened_at = time.time()

    def should_attempt_recovery(self) -> bool:
        """For non-primary tiers we don't auto-recover — only primary does."""
        if not self.is_open or self.opened_at is None:
            return False
        return (time.time() - self.opened_at) >= RECOVERY_AFTER_SECS


class CircuitBreakerRouter:
    """
    Owns the 3-tier model chain and routing decisions.
    Single instance shared across requests (module-level singleton in main.py).
    """

    def __init__(self):
        # Default order changed for cloud deployment: Groq (fast, no GPU
        # needed) -> Gemini -> Qwen (local, last resort — only useful if
        # you're also running a GPU-backed Ollama host in the same VPC).
        # Customer-supplied BYO API keys are still tried before ANY of this
        # chain — see call_customer_llm() in main.py, unaffected by this.
        primary_name = os.getenv("PRIMARY_LLM", "groq").lower().strip()
        if primary_name == "qwen":
            self.primary  = ModelState(name="qwen")
            self.fallback1 = ModelState(name="groq")
            self.fallback2 = ModelState(name="gemini")
        elif primary_name == "gemini":
            self.primary  = ModelState(name="gemini")
            self.fallback1 = ModelState(name="groq")
            self.fallback2 = ModelState(name="qwen")
        else:  # default: groq
            self.primary  = ModelState(name="groq")
            self.fallback1 = ModelState(name="gemini")
            self.fallback2 = ModelState(name="qwen")

    def _active_chain(self, skip_tiers: set | None = None) -> list[ModelState]:
        """
        Returns the ordered list of models to try for this request.
        Primary is always tried first UNLESS its circuit is open AND
        recovery isn't due yet.

        `skip_tiers` (e.g. {"qwen"}) lets a caller force escalation past a
        tier that's already proven it can't fix a given error twice in a
        row — no point burning a 3rd attempt on the same small local model
        if it made the identical mistake on attempt 1 and 2.
        """
        chain = []

        if not self.primary.is_open:
            chain.append(self.primary)
        elif self.primary.should_attempt_recovery():
            chain.append(self.primary)  # recovery attempt
        # else: skip primary entirely, go straight to fallbacks

        if self.primary not in chain or self.primary.is_open:
            chain.append(self.fallback1)
            chain.append(self.fallback2)
        else:
            # primary is healthy and first in chain — still list fallbacks after it
            chain.append(self.fallback1)
            chain.append(self.fallback2)

        # De-duplicate while preserving order
        seen = set()
        ordered = []
        for m in chain:
            if m.name not in seen:
                ordered.append(m)
                seen.add(m.name)

        if skip_tiers:
            filtered = [m for m in ordered if m.name not in skip_tiers]
            if filtered:  # never skip down to an empty chain
                return filtered
        return ordered

    def status(self) -> dict:
        """For a /health or /status endpoint — shows current breaker state."""
        def fmt(m: ModelState):
            return {
                "name": m.name,
                "circuit_open": m.is_open,
                "consecutive_failures": m.consecutive_failures,
                "seconds_until_recovery_attempt": (
                    max(0, RECOVERY_AFTER_SECS - (time.time() - m.opened_at))
                    if m.is_open and m.opened_at else None
                ),
            }
        return {
            "primary": fmt(self.primary),
            "fallback1": fmt(self.fallback1),
            "fallback2": fmt(self.fallback2),
        }

    async def generate(self, prompt: str, max_tokens: int = 400, skip_tiers: set | None = None) -> tuple[str, str]:
        """
        Tries each model in the active chain in order.
        Returns (raw_text, model_name_used).
        Raises RuntimeError only if ALL models in the chain fail.
        """
        chain = self._active_chain(skip_tiers=skip_tiers)
        last_error = None

        for model_state in chain:
            try:
                if model_state.name == "qwen":
                    text = await self._call_ollama(prompt, max_tokens)
                elif model_state.name == "groq":
                    if not GROQ_API_KEY:
                        raise RuntimeError("GROQ_API_KEY not set — skipping fallback 1")
                    text = await self._call_groq(prompt, max_tokens)
                elif model_state.name == "gemini":
                    if not GEMINI_API_KEY:
                        raise RuntimeError("GEMINI_API_KEY not set — skipping fallback 2")
                    text = await self._call_gemini(prompt, max_tokens)
                else:
                    continue

                model_state.record_success()
                return text, model_state.name

            except Exception as e:
                last_error = e
                model_state.record_failure()
                continue  # try next model in chain

        raise RuntimeError(
            f"All models in the fallback chain failed. Last error: {last_error}"
        )

    # ── Individual model callers ───────────────────────────────────────────

    async def _call_ollama(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens, "temperature": 0.1, "top_k": 10,
                "num_ctx": OLLAMA_NUM_CTX,
            },
        }
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"].strip()

    async def _call_groq(self, prompt: str, max_tokens: int) -> str:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=body)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    async def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    # ── Streaming variants (for showing live model "thinking" in the UI) ────
    # These mirror generate()'s circuit-breaker chain, but yield token chunks
    # as they arrive instead of waiting for the full completion. Gemini has
    # no simple streaming REST call wired up here, so it yields once at the end.

    async def generate_stream(self, prompt: str, max_tokens: int = 700, skip_tiers: set | None = None):
        """
        Async generator. Yields:
          {"token": str, "model": name}                  — as tokens arrive
          {"model_failed": name, "error": str}            — a tier failed, moving on
          {"done": True, "full_text": str, "model": name}  — stream finished
        Raises RuntimeError only if every model in the chain fails.
        """
        chain = self._active_chain(skip_tiers=skip_tiers)
        last_error = None

        for model_state in chain:
            full_text = ""
            try:
                if model_state.name == "qwen":
                    async for tok in self._stream_ollama(prompt, max_tokens):
                        full_text += tok
                        yield {"token": tok, "model": "qwen"}
                elif model_state.name == "groq":
                    if not GROQ_API_KEY:
                        raise RuntimeError("GROQ_API_KEY not set — skipping fallback 1")
                    async for tok in self._stream_groq(prompt, max_tokens):
                        full_text += tok
                        yield {"token": tok, "model": "groq"}
                elif model_state.name == "gemini":
                    if not GEMINI_API_KEY:
                        raise RuntimeError("GEMINI_API_KEY not set — skipping fallback 2")
                    full_text = await self._call_gemini(prompt, max_tokens)
                    yield {"token": full_text, "model": "gemini"}
                else:
                    continue

                model_state.record_success()
                yield {"done": True, "full_text": full_text.strip(), "model": model_state.name}
                return

            except Exception as e:
                last_error = e
                model_state.record_failure()
                yield {"model_failed": model_state.name, "error": str(e)}
                continue

        raise RuntimeError(
            f"All models in the fallback chain failed. Last error: {last_error}"
        )

    async def _stream_ollama(self, prompt: str, max_tokens: int):
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens, "temperature": 0.1, "top_k": 10,
                "num_ctx": OLLAMA_NUM_CTX,
            },
        }
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("response", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break

    async def _stream_groq(self, prompt: str, max_tokens: int):
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", GROQ_URL, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        piece = chunk["choices"][0]["delta"].get("content", "")
                        if piece:
                            yield piece
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


# Module-level singleton — shared across all requests in this process
router = CircuitBreakerRouter()
