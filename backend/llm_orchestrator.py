"""Single request-scoped LLM routing, retry, breaker, and failure-log path."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import httpx
from filelock import FileLock

from backend.llm_config import RuntimeConfigSnapshot, runtime_config
from backend.llm_key_store import get_active_credentials
from backend.llm_registry import PROVIDERS, ProviderDefinition, get_provider


CredentialSource = Literal["byo", "system"]


@dataclass(frozen=True)
class CredentialIdentity:
    tenant_id: str
    source: CredentialSource
    provider: str
    key_reference: str
    model: str

    @property
    def breaker_key(self) -> tuple[str, str, str, str]:
        return (self.tenant_id, self.source, self.provider, self.key_reference)


@dataclass(frozen=True)
class ResolvedCredential:
    identity: CredentialIdentity
    secret: Optional[str]
    endpoint: str
    provider_definition: ProviderDefinition
    ollama_num_ctx: int | None = None


class ProviderCallError(RuntimeError):
    def __init__(self, error_type: str, *, status_code: int | None = None, retry_after: float | None = None, response_text: str | None = None):
        self.error_type = error_type
        self.status_code = status_code
        self.retry_after = retry_after
        self.response_text = response_text
        detail = f" ({status_code}): {response_text}" if status_code and response_text else f" ({status_code})" if status_code else ""
        super().__init__(f"{error_type}{detail}")


class AllProvidersFailed(RuntimeError):
    pass


@dataclass
class BreakerState:
    consecutive_failures: int = 0
    open_until: float = 0.0
    blocked: bool = False
    last_error_type: str | None = None


class CredentialBreakerStore:
    """Process-local breaker state isolated by tenant, source, provider, and key version."""

    _AUTH_COOLDOWN = 60  # seconds before retrying after auth/request errors

    def __init__(self, threshold: int = 3, recovery_seconds: int = 300) -> None:
        self._threshold = threshold
        self._recovery_seconds = recovery_seconds
        self._states: dict[tuple[str, str, str, str], BreakerState] = {}
        self._lock = threading.RLock()

    def allow(self, identity: CredentialIdentity) -> bool:
        with self._lock:
            state = self._states.get(identity.breaker_key)
            if not state:
                return True
            now = time.monotonic()
            if state.open_until > now:
                return False

            # A cooldown has elapsed.  Clear its state before allowing the
            # next request so the provider is both retried and accurately
            # reported as recovered.
            if state.blocked or state.open_until:
                self._states.pop(identity.breaker_key, None)
            return True

    def record_success(self, identity: CredentialIdentity) -> None:
        with self._lock:
            self._states[identity.breaker_key] = BreakerState()

    def record_failure(self, identity: CredentialIdentity, error: ProviderCallError) -> BreakerState:
        with self._lock:
            state = self._states.setdefault(identity.breaker_key, BreakerState())
            state.last_error_type = error.error_type
            if error.error_type in {"auth", "request", "malformed_response"}:
                # Timed cooldown instead of permanent block — auto-recovers
                # after key rotation without needing a server restart
                state.blocked = True
                state.open_until = time.monotonic() + self._AUTH_COOLDOWN
                return state
            if error.error_type == "rate_limit":
                cooldown = error.retry_after or self._recovery_seconds
                state.open_until = max(state.open_until, time.monotonic() + max(5.0, cooldown))
                return state
            state.consecutive_failures += 1
            if state.consecutive_failures >= self._threshold:
                cooldown = error.retry_after or self._recovery_seconds
                state.open_until = time.monotonic() + max(1.0, cooldown)
            return state

    def reset_tenant_provider(self, tenant_id: str, provider: str) -> None:
        with self._lock:
            keys_to_delete = [
                key for key in self._states.keys()
                if key[0] == tenant_id and key[2] == provider
            ]
            for key in keys_to_delete:
                del self._states[key]

    def status(self, tenant_id: str | None) -> dict:
        now = time.monotonic()
        with self._lock:
            entries = {}
            for key, state in self._states.items():
                tenant, source, provider, key_reference = key
                if tenant_id and tenant != tenant_id:
                    continue
                seconds_until_recovery = max(0, round(state.open_until - now, 1))
                entries[f"{source}:{provider}:{key_reference}"] = {
                    "tenant": tenant,
                    "source": source,
                    "provider": provider,
                    "key_reference": key_reference,
                    "blocked": state.blocked and seconds_until_recovery > 0,
                    "consecutive_failures": state.consecutive_failures,
                    "seconds_until_recovery": seconds_until_recovery,
                    "last_error_type": state.last_error_type,
                }
            return entries


class RetryPolicy:
    max_attempts = 3

    @staticmethod
    def should_retry(error: ProviderCallError, attempt: int) -> bool:
        if error.error_type in {"timeout", "network", "rate_limit"}:
            return False  # Instant failover to next model in fallback chain — 0 retries
        return attempt < RetryPolicy.max_attempts and error.error_type == "service"

    @staticmethod
    def delay_seconds(error: ProviderCallError, attempt: int) -> float:
        if error.retry_after is not None:
            return min(max(error.retry_after, 0.0), 2.0)
        return min(2.0, (2 ** (attempt - 1)) + random.uniform(0, 0.25))


class PersistentFailureLog:
    def write(self, path: Path, event: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(path.with_suffix(path.suffix + ".lock")), timeout=10)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        with lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


class ProviderGateway:
    async def invoke(
        self,
        credential: ResolvedCredential,
        prompt: str,
        max_tokens: int,
        image: tuple[str, str] | None = None,
    ) -> str:
        try:
            timeout = self._timeout_for(credential.provider_definition.style, image is not None)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await self._request(client, credential, prompt, max_tokens, image)
                response.raise_for_status()
                return self._parse_response(credential.provider_definition.style, response)
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc.response) from None
        except httpx.TimeoutException:
            raise ProviderCallError("timeout") from None
        except httpx.RequestError:
            raise ProviderCallError("network") from None
        except ProviderCallError:
            raise

    @staticmethod
    def _timeout_for(style: str, has_image: bool) -> httpx.Timeout:
        if style == "ollama":
            return httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0)
        read_timeout = 120.0 if has_image else 60.0
        return httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=30.0)

    async def _request(
        self,
        client: httpx.AsyncClient,
        credential: ResolvedCredential,
        prompt: str,
        max_tokens: int,
        image: tuple[str, str] | None,
    ) -> httpx.Response:
        definition = credential.provider_definition
        identity = credential.identity
        if definition.style == "openai":
            return await client.post(
                credential.endpoint,
                headers={"Authorization": f"Bearer {credential.secret}", "Content-Type": "application/json"},
                json={"model": identity.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.1},
            )
        if definition.style == "anthropic":
            return await client.post(
                credential.endpoint,
                headers={"x-api-key": credential.secret or "", "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": identity.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
            )
        if definition.style == "gemini":
            parts = [{"text": prompt}]
            if image:
                mime_type, image_data = image
                parts.append({"inlineData": {"mimeType": mime_type, "data": image_data}})
            return await client.post(
                f"{credential.endpoint.rstrip('/')}/{identity.model}:generateContent",
                params={"key": credential.secret or ""},
                json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}},
            )
        if definition.style == "ollama":
            options = {"num_predict": max_tokens, "temperature": 0.1}
            if credential.ollama_num_ctx:
                options["num_ctx"] = credential.ollama_num_ctx
            return await client.post(
                f"{credential.endpoint.rstrip('/')}/api/generate",
                json={"model": identity.model, "prompt": prompt, "stream": False, "options": options},
            )
        raise ProviderCallError("request")

    @staticmethod
    def _parse_response(style: str, response: httpx.Response) -> str:
        try:
            data = response.json()
            if style == "anthropic":
                text = data["content"][0]["text"]
            elif style == "gemini":
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            elif style == "ollama":
                text = data["response"]
            else:
                msg = data["choices"][0]["message"]
                text = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty response")
            return text.strip()
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ProviderCallError("malformed_response") from None

    @staticmethod
    def _http_error(response: httpx.Response) -> ProviderCallError:
        status = response.status_code
        retry_after = None
        text_snippet = response.text[:120].strip() if response.text else ""
        if status == 429:
            try:
                retry_after = float(response.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = None
            return ProviderCallError("rate_limit", status_code=status, retry_after=retry_after, response_text=text_snippet)
        if status in {401, 403}:
            return ProviderCallError("auth", status_code=status, response_text=text_snippet)
        if status in {400, 404, 422}:
            return ProviderCallError("request", status_code=status, response_text=text_snippet)
        if status >= 500:
            return ProviderCallError("service", status_code=status, response_text=text_snippet)
        return ProviderCallError("request", status_code=status, response_text=text_snippet)


class CredentialResolver:
    _byo_priority = ("openai", "anthropic", "deepseek", "groq", "gemini", "ollama")

    def resolve(self, tenant_id: str | None, capability: str, snapshot: RuntimeConfigSnapshot) -> list[ResolvedCredential]:
        normalized_tenant = (tenant_id or "").strip() or "unscoped"
        candidates = self._byo_candidates(normalized_tenant, capability, snapshot)
        candidates.extend(self._system_candidates(normalized_tenant, capability, snapshot))
        return candidates

    def _byo_candidates(
        self,
        tenant_id: str,
        capability: str,
        snapshot: RuntimeConfigSnapshot,
    ) -> list[ResolvedCredential]:
        if tenant_id == "unscoped":
            return []
        credentials = {credential.provider: credential for credential in get_active_credentials(tenant_id)}
        candidates = []
        for provider in self._byo_priority:
            credential = credentials.get(provider)
            if not credential:
                continue
            definition = get_provider(provider)
            if capability not in definition.capabilities:
                continue
            endpoint = credential.api_key.rstrip("/") if provider == "ollama" else definition.endpoint
            secret = None if provider == "ollama" else credential.api_key
            candidates.append(ResolvedCredential(
                identity=CredentialIdentity(tenant_id, "byo", provider, credential.key_reference, credential.model),
                secret=secret,
                endpoint=endpoint,
                provider_definition=definition,
                ollama_num_ctx=snapshot.ollama_num_ctx if provider == "ollama" else None,
            ))
        return candidates

    def _system_candidates(self, tenant_id: str, capability: str, snapshot: RuntimeConfigSnapshot) -> list[ResolvedCredential]:
        providers = ["gemini"] if capability == "vision" else snapshot.chain()
        candidates = []
        for provider in providers:
            definition = get_provider(provider)
            if capability not in definition.capabilities:
                continue
            secret, model, endpoint = self._system_values(provider, snapshot)
            if provider != "ollama" and not secret:
                continue
            fingerprint_source = secret or endpoint
            fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:16]
            candidates.append(ResolvedCredential(
                identity=CredentialIdentity(tenant_id, "system", provider, f"system:{provider}:{fingerprint}", model),
                secret=secret,
                endpoint=endpoint,
                provider_definition=definition,
                ollama_num_ctx=snapshot.ollama_num_ctx if provider == "ollama" else None,
            ))
        return candidates

    @staticmethod
    def _system_values(provider: str, snapshot: RuntimeConfigSnapshot) -> tuple[str | None, str, str]:
        if provider == "groq":
            return snapshot.groq_api_key, snapshot.groq_model, get_provider("groq").endpoint
        if provider == "gemini":
            return snapshot.gemini_api_key, snapshot.gemini_model, get_provider("gemini").endpoint
        if provider == "ollama":
            return None, snapshot.ollama_model, snapshot.ollama_base_url
        raise ValueError(f"Unsupported system provider: {provider}")


class LLMOrchestrator:
    def __init__(self) -> None:
        self._resolver = CredentialResolver()
        self._gateway = ProviderGateway()
        self._breakers = CredentialBreakerStore()
        self._failure_log = PersistentFailureLog()

    async def generate(
        self,
        prompt: str,
        *,
        tenant_id: str | None,
        max_tokens: int = 400,
        capability: str = "chat",
        image: tuple[str, str] | None = None,
    ) -> tuple[str, str]:
        snapshot = runtime_config.snapshot()
        request_id = uuid.uuid4().hex
        candidates = self._resolver.resolve(tenant_id, capability, snapshot)
        if not candidates:
            raise AllProvidersFailed("No configured credential supports this request.")
        errors: list[str] = []
        for credential in candidates:
            if not self._breakers.allow(credential.identity):
                errors.append(f"{credential.identity.source}:{credential.identity.provider}:breaker_open")
                self._log_failure(snapshot, request_id, credential.identity, capability, "breaker_open", None, 0, "skipped")
                continue
            try:
                text, attempts = await self._invoke_with_retry(credential, prompt, max_tokens, image)
                self._breakers.record_success(credential.identity)
                return text, self._label(credential.identity)
            except ProviderCallError as error:
                state = self._breakers.record_failure(credential.identity, error)
                action = "blocked" if state.blocked else "opened" if state.open_until > time.monotonic() else "fallback"
                self._log_failure(snapshot, request_id, credential.identity, capability, error.error_type, error.status_code, getattr(error, "attempts", 1), action)
                errors.append(f"{credential.identity.source}:{credential.identity.provider}:{error.error_type}")
        raise AllProvidersFailed("All LLM candidates failed: " + ", ".join(errors))

    async def validate_key(self, provider: str, api_key: str, model: str = "") -> dict:
        provider = provider.strip().lower()
        if provider not in PROVIDERS:
            return {"valid": False, "error": f"Unknown provider: {provider}"}
        api_key = (api_key or "").strip()
        if provider != "ollama" and not api_key:
            return {"valid": False, "error": "API key is required"}
        definition = get_provider(provider)
        model = (model or "").strip() or definition.default_model
        endpoint = api_key.rstrip("/") if provider == "ollama" else definition.endpoint
        secret = None if provider == "ollama" else api_key
        fingerprint = hashlib.sha256((api_key or endpoint).encode()).hexdigest()[:16]
        snapshot = runtime_config.snapshot()
        credential = ResolvedCredential(
            identity=CredentialIdentity("validation", "byo", provider, f"validation:{provider}:{fingerprint}", model),
            secret=secret,
            endpoint=endpoint,
            provider_definition=definition,
            ollama_num_ctx=snapshot.ollama_num_ctx if provider == "ollama" else None,
        )
        request_id = uuid.uuid4().hex
        try:
            await self._invoke_with_retry(credential, "Reply with the single word: OK", 100, None)
            return {"valid": True}
        except ProviderCallError as error:
            self._log_failure(
                snapshot,
                request_id,
                credential.identity,
                "validation",
                error.error_type,
                error.status_code,
                getattr(error, "attempts", 1),
                "validation",
            )
            if error.error_type == "auth":
                return {"valid": False, "error": f"Invalid API key (HTTP {error.status_code})."}
            return {"valid": False, "error": self._friendly_error(error)}

    async def analyze_dashboard(self, image_b64: str, tenant_id: str | None) -> list[dict]:
        mime_type, image_data = self._split_image(image_b64)
        prompt = (
            "Analyze this image carefully. Count how many distinct charts or visualizations are present.\n\n"
            "For EACH chart, output exactly:\n--- CHART N ---\nType: <chart type>\nData: <data requirements>\n\n"
            "Number charts from 1 and list data requirements, not styling details."
        )
        raw, _ = await self.generate(
            prompt,
            tenant_id=tenant_id,
            max_tokens=700,
            capability="vision",
            image=(mime_type, image_data),
        )
        return self._parse_dashboard_response(raw)

    async def _invoke_with_retry(
        self,
        credential: ResolvedCredential,
        prompt: str,
        max_tokens: int,
        image: tuple[str, str] | None,
    ) -> tuple[str, int]:
        for attempt in range(1, RetryPolicy.max_attempts + 1):
            try:
                return await self._gateway.invoke(credential, prompt, max_tokens, image), attempt
            except ProviderCallError as error:
                if not RetryPolicy.should_retry(error, attempt):
                    error.attempts = attempt
                    raise
                await asyncio.sleep(RetryPolicy.delay_seconds(error, attempt))
        raise ProviderCallError("service")

    def status(self, tenant_id: str | None) -> dict:
        normalized_tenant = (tenant_id or "").strip() or "unscoped"
        return {"tenant_id": normalized_tenant, "breakers": self._breakers.status(normalized_tenant)}

    def reset_breaker(self, tenant_id: str, provider: str) -> None:
        normalized_tenant = (tenant_id or "").strip() or "unscoped"
        self._breakers.reset_tenant_provider(normalized_tenant, provider)

    @staticmethod
    def _label(identity: CredentialIdentity) -> str:
        source = "BYO" if identity.source == "byo" else "System"
        return f"{source} {get_provider(identity.provider).display_name} ({identity.model})"

    @staticmethod
    def _friendly_error(error: ProviderCallError) -> str:
        if error.error_type == "rate_limit":
            return "Provider rate limit reached."
        if error.error_type == "timeout":
            return "Provider request timed out."
        if error.error_type == "network":
            return "Cannot reach the provider API."
        if error.error_type == "request":
            return f"Provider rejected the model or request (HTTP {error.status_code})."
        if error.error_type == "malformed_response":
            return "Provider returned an invalid response."
        return "Provider request failed."

    def _log_failure(
        self,
        snapshot: RuntimeConfigSnapshot,
        request_id: str,
        identity: CredentialIdentity,
        capability: str,
        error_type: str,
        status_code: int | None,
        attempts: int,
        breaker_action: str,
    ) -> None:
        try:
            self._failure_log.write(snapshot.failure_log_path, {
                "request_id": request_id,
                "tenant_id": identity.tenant_id,
                "source": identity.source,
                "provider": identity.provider,
                "key_reference": identity.key_reference,
                "model": identity.model,
                "capability": capability,
                "lifecycle_stage": "api_call",
                "error_type": error_type,
                "http_status": status_code,
                "attempts": attempts,
                "breaker_action": breaker_action,
            })
        except Exception:
            pass

    @staticmethod
    def _split_image(image_b64: str) -> tuple[str, str]:
        if "," not in image_b64:
            return "image/jpeg", image_b64
        header, image_data = image_b64.split(",", 1)
        mime_match = re.match(r"data:([^;]+);base64", header, re.IGNORECASE)
        return (mime_match.group(1) if mime_match else "image/jpeg"), image_data

    @staticmethod
    def _parse_dashboard_response(raw: str) -> list[dict]:
        blocks = re.split(r"---\s*CHART\s+(\d+)\s*---", raw, flags=re.IGNORECASE)
        charts: list[dict] = []
        index = 1
        while index < len(blocks) - 1:
            body = blocks[index + 1].strip()
            chart_type = ""
            description = ""
            for line in body.splitlines():
                line = line.strip()
                if line.lower().startswith("type:"):
                    chart_type = line[5:].strip()
                elif line.lower().startswith("data:"):
                    description = line[5:].strip()
            charts.append({"chart_number": int(blocks[index]), "chart_type": chart_type, "description": description or body})
            index += 2
        return charts or [{"chart_number": 1, "chart_type": "", "description": raw}]


orchestrator = LLMOrchestrator()
