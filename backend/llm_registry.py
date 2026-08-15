"""Provider definitions shared by routing, validation, and the settings catalog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ProviderStyle = Literal["openai", "anthropic", "gemini", "ollama"]


@dataclass(frozen=True)
class ProviderDefinition:
    provider: str
    display_name: str
    style: ProviderStyle
    models: tuple[str, ...]
    capabilities: frozenset[str]
    endpoint: str

    @property
    def default_model(self) -> str:
        return self.models[0]


PROVIDERS: dict[str, ProviderDefinition] = {
    "openai": ProviderDefinition(
        provider="openai",
        display_name="OpenAI",
        style="openai",
        models=("gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"),
        capabilities=frozenset({"chat"}),
        endpoint="https://api.openai.com/v1/chat/completions",
    ),
    "anthropic": ProviderDefinition(
        provider="anthropic",
        display_name="Anthropic (Claude)",
        style="anthropic",
        models=("claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"),
        capabilities=frozenset({"chat"}),
        endpoint="https://api.anthropic.com/v1/messages",
    ),
    "deepseek": ProviderDefinition(
        provider="deepseek",
        display_name="DeepSeek",
        style="openai",
        models=("deepseek-chat", "deepseek-coder", "deepseek-reasoner"),
        capabilities=frozenset({"chat"}),
        endpoint="https://api.deepseek.com/chat/completions",
    ),
    "groq": ProviderDefinition(
        provider="groq",
        display_name="Groq",
        style="openai",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3.6-27b", "openai/gpt-oss-120b"),
        capabilities=frozenset({"chat"}),
        endpoint="https://api.groq.com/openai/v1/chat/completions",
    ),
    "gemini": ProviderDefinition(
        provider="gemini",
        display_name="Google Gemini",
        style="gemini",
        models=("gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"),
        capabilities=frozenset({"chat", "vision"}),
        endpoint="https://generativelanguage.googleapis.com/v1beta/models",
    ),
    "ollama": ProviderDefinition(
        provider="ollama",
        display_name="Ollama (Local)",
        style="ollama",
        models=("qwen2.5-coder:7b", "llama3.2", "qwen2.5:7b"),
        capabilities=frozenset({"chat"}),
        endpoint="http://localhost:11434",
    ),
}


def get_provider(provider: str) -> ProviderDefinition:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unknown provider: {provider}") from exc


def provider_catalog() -> dict[str, dict]:
    """Return a JSON-safe settings catalog derived only from this registry."""
    catalog: dict[str, dict] = {}
    for provider, definition in PROVIDERS.items():
        payload = asdict(definition)
        payload.pop("style", None)
        payload.pop("capabilities", None)
        payload.pop("endpoint", None)
        payload["name"] = payload.pop("display_name")
        payload["models"] = list(payload["models"])
        catalog[provider] = payload
    return catalog
