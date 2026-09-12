"""
mag.memory — Memory-Augmented Generation, complementing curriculum.graph's RAG.

Phase 1 (pre-generation): retrieves a query-adaptive slice of this learner's
own interaction history — graph-traversed, not just similarity-searched —
and returns it as memory_context for tutor_runtime/prompt.py.

Phase 3 (post-generation): fast-path ingests the just-completed turn as a
new event node (Algorithm 2), then fires the slow-path consolidation
(Algorithm 3) as a background task so it never adds latency to the child's
response.
"""
from __future__ import annotations

import asyncio

from config import Config
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.learner_state.signals import extract as extract_signals
from modules.mag_memory import ingest, retrieval
from modules.mag_memory.graph import _get_collection, run_chroma

log = get_logger("mag.memory")

# asyncio only holds a *weak* reference to a task created via create_task —
# with nothing else referencing it, it can be garbage-collected mid-run
# before it ever writes anything. Keep a strong reference here until each
# task finishes, same fix needed for (but predating this module in)
# learner_state/module.py's _consult_krishna.
_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _consolidate_in_background(
    node_id: str, learner_id: str, content: str, concept_ids: list[str],
):
    """Opens its own connection — the request's ctx.db is gone by the time
    this runs. Mirrors learner_state/module.py's _consult_krishna pattern."""
    try:
        from foundation.db import get_pool
        from modules.mag_memory.consolidate import consolidate_node
        pool = await get_pool()
        await consolidate_node(pool, node_id, learner_id, content, concept_ids)
    except Exception as e:
        log.warning("mag_consolidation_background_failed", learner_id=learner_id, error=str(e))


class MagMemoryModule(Module):
    name = "mag.memory"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        if not Config.MAG_ENABLED:
            # Full kill switch — retrieval.build_memory_context already checks
            # this too, but skip ingestion entirely as well so disabling MAG
            # actually stops all writes/Ollama calls, not just prompt use.
            return ModuleResult(data={})

        if not ctx.response_text:
            # ── Phase 1: pre-generation ────────────────────────────────────
            memory_context = await retrieval.build_memory_context(ctx.db, ctx.learner_id, ctx.message)
            return ModuleResult(data={"memory_context": memory_context})

        # ── Phase 3: post-generation ────────────────────────────────────────
        signals = extract_signals(ctx.message)
        concept_ids = signals["concepts"] + signals["domains"]
        # wonder.engine runs before this module in both phases (kernel/router.py) —
        # tag the node so its own consolidation can later surface whether this
        # tangent connected back to a concept the child went on to master.
        wonder_puzzle = ctx.module_data.get("wonder.engine", {}).get("puzzle_offered")
        if wonder_puzzle:
            concept_ids = concept_ids + [f"_wonder:{wonder_puzzle}"]
        concept_ids = list(dict.fromkeys(concept_ids))  # dedup, keep order

        node_id, content = await ingest.ingest_turn(
            ctx.db, ctx.learner_id, ctx.request_id,
            ctx.message, ctx.response_text, concept_ids,
        )
        if node_id:
            _fire_and_forget(ingest.embed_node(node_id, ctx.learner_id, content))
            _fire_and_forget(_consolidate_in_background(node_id, ctx.learner_id, content, concept_ids))

        return ModuleResult(data={"node_id": node_id})

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        await ctx.db.execute("DELETE FROM mag_memory.nodes WHERE learner_id = $1", learner_id)
        try:
            await run_chroma(lambda: _get_collection().delete(where={"learner_id": learner_id}))
        except Exception as e:
            log.warning("mag_chroma_erase_failed", learner_id=learner_id, error=str(e))
        log.info("mag_memory_erased", learner_id=learner_id)
