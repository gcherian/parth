"""Kernel module that injects meaning graph context before tutor generation."""
from __future__ import annotations

from foundation.observability import get_logger
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from modules.meaning_graph.service import age_for_grade, context_for_message

log = get_logger("meaning.graph")


class MeaningGraphModule(Module):
    name = "meaning.graph"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        if ctx.response_text or not ctx.moderation_ok:
            return ModuleResult(data={})

        age = age_for_grade(ctx.grade)
        try:
            meaning_context = await context_for_message(ctx.db, ctx.message, age=age)
        except Exception as exc:
            log.warning("meaning_context_failed", error=str(exc))
            meaning_context = ""

        return ModuleResult(data={
            "age": age,
            "meaning_context": meaning_context,
            "matched": bool(meaning_context),
        })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass
