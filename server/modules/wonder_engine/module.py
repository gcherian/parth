"""
wonder.engine — offers cross-domain discovery detours during ordinary
chat, and reframes misconceptions as reasoning worth investigating rather
than errors to fix. Additive: curriculum.graph's RAG and MAG's memory
graph are untouched, and this module never replaces answering what the
child actually asked — see bridges.py's prompt text.

Phase 1 (pre-generation): checks learner.state's misconception_hint and
this session's curiosity heat (learner_state/curiosity.py, unchanged);
if a real signal is present and the cadence gate allows it, builds one
optional context block for tutor_runtime/prompt.py.

Phase 3 (post-generation): re-publishes which puzzle (if any) was offered
this turn so mag.memory (which runs after this module in both phases)
can tag the resulting memory node — a wonder turn is then traceable
through MAG's existing causal-edge consolidation over time. Engagement
detection (did the child actually take up the offer) is not implemented
yet — see docs/paradigm_shift_2026_08_29.md.
"""
from __future__ import annotations

from config import Config
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.learner_state import curiosity
from modules.wonder_engine import bridges, store

log = get_logger("wonder.engine")


class WonderEngineModule(Module):
    name = "wonder.engine"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        if not Config.WONDER_ENABLED:
            return ModuleResult(data={})
        if not ctx.response_text:
            return await self._pre(ctx)
        return await self._post(ctx)

    async def _pre(self, ctx: KernelContext) -> ModuleResult:
        parts: list[str] = []
        puzzle_offered: str | None = None
        sphere_offered: str | None = None

        misconception_hint = ctx.module_data.get("learner.state", {}).get("misconception_hint", "")
        if misconception_hint:
            parts.append(bridges.format_belief_exploration(misconception_hint))

        try:
            threads = await curiosity.load(ctx.db, ctx.learner_id, ctx.session_id)
            dominant = curiosity.dominant_thread(threads)
            if dominant and dominant["heat"] >= Config.WONDER_HEAT_THRESHOLD:
                too_soon = await store.too_soon_for_another_offer(
                    ctx.db, ctx.learner_id, Config.WONDER_MIN_MINUTES_BETWEEN_OFFERS
                )
                if not too_soon:
                    exclude = await store.recently_offered_puzzle_ids(ctx.db, ctx.learner_id)
                    puzzle = bridges.select_bridge_puzzle(ctx.subject, ctx.grade, exclude)
                    if puzzle:
                        parts.append(bridges.format_wonder_offer(puzzle))
                        puzzle_offered, sphere_offered = puzzle["id"], puzzle["sphere"]
                        await store.record_offer(ctx.db, ctx.learner_id, puzzle["id"], puzzle["sphere"])
        except Exception as e:
            log.warning("wonder_curiosity_check_failed", learner_id=ctx.learner_id, error=str(e))

        return ModuleResult(data={
            "wonder_context": "\n\n".join(parts),
            "puzzle_offered": puzzle_offered,
            "sphere_offered": sphere_offered,
        })

    async def _post(self, ctx: KernelContext) -> ModuleResult:
        # Preserve puzzle_offered across this phase's own module_data slot
        # (see mag.memory's module.py, which reads it after this module
        # runs, in the same Sequential post-generation step).
        prior = ctx.module_data.get("wonder.engine", {})
        return ModuleResult(data={"puzzle_offered": prior.get("puzzle_offered")})

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        await ctx.db.execute("DELETE FROM wonder_engine.offers WHERE learner_id = $1", learner_id)
