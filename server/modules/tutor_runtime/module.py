"""
tutor.runtime — The only module that knows which LLM backend is in use.

Receives KernelContext with learner_context + curriculum_context already filled
by Phase 1 modules, assembles the prompt, calls the LLM, and returns the response.

Backend selection (Config.TUTOR_BACKEND):
  "auto"       → Anthropic if ANTHROPIC_API_KEY is set, else Ollama
  "anthropic"  → Always use Claude (cloud / pilot mode)
  "ollama"     → Always use local Ollama (dev / offline mode)
"""
import json
import re

import httpx

from config import Config
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.tutor_runtime.prompt import build_system_prompt, build_messages, build_anthropic_messages
from modules.tutor_runtime.verifier import verify_math

log = get_logger("tutor.runtime")

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


def _pick_temperature(psyche: dict | None) -> float:
    if not psyche or psyche.get("sample_count", 0) < 3:
        return 0.7
    anxiety = psyche.get("anxiety", 0.5)
    depth = psyche.get("depth_preference", 0.5)
    base = 0.7 - (anxiety - 0.5) * 0.4 + (depth - 0.5) * 0.2
    return round(max(0.3, min(0.95, base)), 2)


class TutorRuntimeModule(Module):
    name = "tutor.runtime"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        if ctx.response_text or not ctx.moderation_ok:
            return ModuleResult(data={})

        psyche = ctx.module_data.get("learner.state", {}).get("psyche")
        temperature = _pick_temperature(psyche)
        use_anthropic = Config.use_anthropic_tutor()

        log.info("llm_call",
                 backend="anthropic" if use_anthropic else "ollama",
                 model=Config.TUTOR_MODEL if use_anthropic else Config.FAST_MODEL,
                 subject=ctx.subject,
                 grade=ctx.grade,
                 temperature=temperature)

        if use_anthropic:
            reply, model_used = await self._call_anthropic(ctx, temperature)
        else:
            system_prompt = build_system_prompt(ctx)
            messages = build_messages(ctx, system_prompt)
            reply, model_used = await self._call_ollama(Config.FAST_MODEL, messages, temperature)

        # ── Math verification ──────────────────────────────────────────────────
        is_correct, math_error = await verify_math(reply, model_used if not use_anthropic else None)
        if not is_correct:
            log.warning("math_error_detected", model=model_used, error=math_error,
                        learner_id=ctx.learner_id)
            if use_anthropic:
                corrected_ctx = _ctx_with_math_correction(ctx, math_error)
                retry_reply, retry_model = await self._call_anthropic(corrected_ctx, temperature)
            else:
                system_prompt = build_system_prompt(ctx)
                retry_msgs = build_messages(ctx, system_prompt)
                if retry_msgs and retry_msgs[-1]["role"] == "user":
                    retry_msgs[-1] = {
                        "role": "user",
                        "content": retry_msgs[-1]["content"]
                        + f"\n\nNote: your previous attempt had this error: {math_error}. Please correct it.",
                    }
                retry_reply, retry_model = await self._call_ollama(
                    Config.FAST_MODEL, retry_msgs, temperature
                )
            retry_correct, _ = await verify_math(
                retry_reply, retry_model if not use_anthropic else None
            )
            if retry_correct:
                reply, model_used, is_correct = retry_reply, retry_model, True
            else:
                log.warning("math_retry_also_failed", learner_id=ctx.learner_id,
                            msg="Failing open — returning original reply.")

        return ModuleResult(data={
            "response_text":    reply,
            "model_used":       model_used,
            "response_domains": _detect_domains(reply),
            "math_verified":    is_correct,
        })

    # ── Anthropic backend ──────────────────────────────────────────────────────

    async def _call_anthropic(self, ctx, temperature: float) -> tuple[str, str]:
        system_prompt, messages = build_anthropic_messages(ctx)
        payload = {
            "model":       Config.TUTOR_MODEL,
            "max_tokens":  1024,
            "temperature": temperature,
            "system":      system_prompt,
            "messages":    messages,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         Config.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    json=payload,
                )
                r.raise_for_status()
                text = r.json()["content"][0]["text"].strip()
                return text, Config.TUTOR_MODEL
        except httpx.TimeoutException:
            log.warning("anthropic_tutor_timeout")
            raise
        except Exception as e:
            log.error("anthropic_tutor_failed", error=str(e))
            raise

    # ── Ollama backend (local dev / offline) ───────────────────────────────────

    async def _call_ollama(self, model: str, messages: list[dict],
                           temperature: float = 0.7) -> tuple[str, str]:
        options = {"temperature": temperature}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{Config.OLLAMA_URL}/api/chat",
                    json={"model": model, "messages": messages, "stream": False,
                          "options": options},
                )
                r.raise_for_status()
                return r.json()["message"]["content"], model
        except httpx.TimeoutException:
            log.warning("ollama_timeout_fallback", model=model)
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(
                        f"{Config.OLLAMA_URL}/api/chat",
                        json={"model": Config.FAST_MODEL, "messages": messages,
                              "stream": False, "options": options},
                    )
                    r.raise_for_status()
                    return r.json()["message"]["content"], Config.FAST_MODEL
            except Exception as e:
                log.error("ollama_fallback_failed", error=str(e))
                raise
        except httpx.ConnectError:
            log.error("ollama_not_running")
            raise

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass


def _ctx_with_math_correction(ctx: KernelContext, math_error: str) -> KernelContext:
    """Return a shallow copy of ctx with the math correction appended to the message."""
    import copy
    corrected = copy.copy(ctx)
    corrected.message = (
        ctx.message
        + f"\n\nNote: your previous attempt had this math error: {math_error}. Please correct it."
    )
    return corrected
