"""Compatibility facade for the unified request-scoped LLM orchestrator."""

from __future__ import annotations

from backend.llm_orchestrator import orchestrator


class ModelRouterFacade:
    async def generate(self, prompt: str, max_tokens: int = 400, tenant_id: str | None = None, **_: object) -> tuple[str, str]:
        return await orchestrator.generate(prompt, tenant_id=tenant_id, max_tokens=max_tokens)

    async def generate_stream(self, prompt: str, max_tokens: int = 700, tenant_id: str | None = None, **_: object):
        text, model = await self.generate(prompt, max_tokens=max_tokens, tenant_id=tenant_id)
        yield {"token": text, "model": model}
        yield {"done": True, "full_text": text, "model": model}

    def status(self, tenant_id: str | None = None) -> dict:
        return orchestrator.status(tenant_id)


router = ModelRouterFacade()
