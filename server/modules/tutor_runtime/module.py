"""
tutor.runtime — The only module that knows Ollama exists.

Receives KernelContext with learner_context + curriculum_context already filled
by Phase 1 modules, assembles the prompt, calls Ollama, and returns the response.
"""
import re

import httpx

from config import Config
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.tutor_runtime.prompt import build_system_prompt, build_messages

log = get_logger("tutor.runtime")

# Analogy domains for lag attribution (detected in response, credited next turn)
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "cricket":   ["cricket", "bat", "wicket", "ipl", "virat"],
    "cooking":   ["cook", "roti", "dal", "sabzi", "kitchen", "boil"],
    "festival":  ["diwali", "holi", "eid", "navratri", "puja"],
    "nature":    ["tree", "leaf", "river", "cloud", "rain", "bird"],
    "transport": ["bus", "auto", "train", "rickshaw", "metro"],
    "gaming":    ["game", "level", "score", "video game"],
    "farming":   ["farm", "crop", "wheat", "harvest", "kisan"],
}


def _detect_domains(text: str) -> list[str]:
    lower = text.lower()
    return [d for d, kws in _DOMAIN_KEYWORDS.items() if any(k in lower for k in kws)]


def _pick_model(message: str, history_len: int, override: str | None) -> str:
    if override:
        return override
    # Use fast model for short/simple queries to reduce latency
    if history_len == 0 and len(message.split()) < 8:
        return Config.FAST_MODEL
    return Config.DEFAULT_MODEL


class TutorRuntimeModule(Module):
    name = "tutor.runtime"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        # This module only acts in Phase 2 (generation)
        # If moderation vetoed, we never get here; if response_text already set, skip
        if ctx.response_text or not ctx.moderation_ok:
            return ModuleResult(data={})

        model_override = event.payload.get("model_override")
        model = _pick_model(ctx.message, len(ctx.history), model_override)

        system_prompt = build_system_prompt(ctx)
        messages = build_messages(ctx, system_prompt)

        log.info("llm_call", model=model, subject=ctx.subject, grade=ctx.grade)

        reply, model_used = await self._call_ollama(model, messages)

        response_domains = _detect_domains(reply)

        return ModuleResult(data={
            "response_text": reply,
            "model_used": model_used,
            "response_domains": response_domains,
        })

    async def _call_ollama(self, model: str, messages: list[dict]) -> tuple[str, str]:
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(
                    f"{Config.OLLAMA_URL}/api/chat",
                    json={"model": model, "messages": messages, "stream": False},
                )
                r.raise_for_status()
                data = r.json()
                return data["message"]["content"], model
        except httpx.TimeoutException:
            log.warning("llm_timeout_fallback", model=model)
            # Fallback to fast model
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(
                        f"{Config.OLLAMA_URL}/api/chat",
                        json={"model": Config.FAST_MODEL, "messages": messages, "stream": False},
                    )
                    r.raise_for_status()
                    data = r.json()
                    return data["message"]["content"], Config.FAST_MODEL
            except Exception as e:
                log.error("llm_fallback_failed", error=str(e))
                raise
        except httpx.ConnectError:
            log.error("ollama_not_running")
            raise

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass  # tutor.runtime holds no per-learner data
