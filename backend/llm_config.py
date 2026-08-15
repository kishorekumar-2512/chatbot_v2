"""Live system LLM configuration with request-safe immutable snapshots."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

from backend.llm_registry import get_provider


DEFAULT_PRIMARY_LLM = "groq"
DEFAULT_OLLAMA_BASE_URL = get_provider("ollama").endpoint
DEFAULT_OLLAMA_MODEL = get_provider("ollama").default_model
CONFIG_KEYS = {
    "PRIMARY_LLM",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "KEY_STORE_PATH",
    "LLM_FAILURE_LOG_PATH",
    "LLM_CONFIG_FILE",
}


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class RuntimeConfigSnapshot:
    primary_llm: str
    groq_api_key: Optional[str]
    groq_model: str
    gemini_api_key: Optional[str]
    gemini_model: str
    ollama_base_url: str
    ollama_model: str
    ollama_num_ctx: int
    key_store_path: Path
    failure_log_path: Path
    revision: str

    def chain(self) -> list[str]:
        if self.primary_llm == "qwen":
            return ["ollama", "groq", "gemini"]
        if self.primary_llm == "gemini":
            return ["gemini", "groq", "ollama"]
        return ["groq", "gemini", "ollama"]


class RuntimeConfig:
    """Refreshes local dotenv configuration on file change without mutating os.environ."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last_revision: str | None = None
        self._last_values: dict[str, str] | None = None
        self._snapshot: RuntimeConfigSnapshot | None = None

    def snapshot(self) -> RuntimeConfigSnapshot:
        with self._lock:
            values, revision = self._read_values()
            if self._snapshot is None or revision != self._last_revision or values != self._last_values:
                self._snapshot = self._build_snapshot(values, revision)
                self._last_revision = revision
                self._last_values = dict(values)
            return self._snapshot

    def _read_values(self) -> tuple[dict[str, str], str]:
        values = {key: value for key in CONFIG_KEYS if (value := os.getenv(key)) is not None}
        config_file = Path(values.get("LLM_CONFIG_FILE", Path(__file__).resolve().parent.parent / ".env"))
        try:
            stat = config_file.stat()
            file_values = dotenv_values(config_file)
            values.update({key: str(value) for key, value in file_values.items() if key in CONFIG_KEYS and value is not None})
            revision = f"{config_file.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
        except FileNotFoundError:
            revision = "environment-only"
        return values, revision

    @staticmethod
    def _build_snapshot(values: dict[str, str], revision: str) -> RuntimeConfigSnapshot:
        project_root = Path(__file__).resolve().parent.parent
        key_store_path = Path(values.get("KEY_STORE_PATH", "./data/llm_keys.json"))
        if not key_store_path.is_absolute():
            key_store_path = project_root / key_store_path
        failure_log_path = Path(values.get("LLM_FAILURE_LOG_PATH", "./data/llm_failures.jsonl"))
        if not failure_log_path.is_absolute():
            failure_log_path = project_root / failure_log_path
        try:
            ollama_num_ctx = int(values.get("OLLAMA_NUM_CTX", "8192"))
        except ValueError:
            ollama_num_ctx = 8192
        return RuntimeConfigSnapshot(
            primary_llm=(_clean(values.get("PRIMARY_LLM")) or DEFAULT_PRIMARY_LLM).lower(),
            groq_api_key=_clean(values.get("GROQ_API_KEY")),
            groq_model=_clean(values.get("GROQ_MODEL")) or get_provider("groq").default_model,
            gemini_api_key=_clean(values.get("GEMINI_API_KEY")),
            gemini_model=_clean(values.get("GEMINI_MODEL")) or get_provider("gemini").default_model,
            ollama_base_url=(_clean(values.get("OLLAMA_BASE_URL")) or DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
            ollama_model=_clean(values.get("OLLAMA_MODEL")) or DEFAULT_OLLAMA_MODEL,
            ollama_num_ctx=ollama_num_ctx,
            key_store_path=key_store_path,
            failure_log_path=failure_log_path,
            revision=revision,
        )


runtime_config = RuntimeConfig()


def system_llm_status() -> dict:
    snapshot = runtime_config.snapshot()
    return {
        "primary_llm": snapshot.primary_llm,
        "fallback_chain": ["qwen" if provider == "ollama" else provider for provider in snapshot.chain()],
        "groq": {"configured": bool(snapshot.groq_api_key), "model": snapshot.groq_model},
        "gemini": {"configured": bool(snapshot.gemini_api_key), "model": snapshot.gemini_model},
        "ollama": {"base_url": snapshot.ollama_base_url, "model": snapshot.ollama_model},
        "any_system_provider_configured": bool(snapshot.groq_api_key or snapshot.gemini_api_key),
        "config_revision": snapshot.revision,
    }


def format_all_models_failed_error(last_error: Optional[Exception | str] = None) -> str:
    status = system_llm_status()
    error_text = str(last_error or "").lower()
    if "rate_limit" in error_text:
        message = "The available LLM providers are temporarily rate-limited. Please wait a minute and try again."
    else:
        message = "No LLM could answer this query. Configure a tenant BYO key or a system provider."
    if last_error:
        message += f" Last error: {str(last_error).strip()}"
    return message + f" System chain: {' -> '.join(status['fallback_chain'])}."
