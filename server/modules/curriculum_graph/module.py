"""
curriculum.graph — Concept graph + NCERT RAG retrieval.

Phase 1 (pre-generation): retrieves semantic context + concept neighbourhood.
"""
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.curriculum_graph.graph import retrieve_semantic, get_concept_neighbourhood
from modules.learner_state.signals import extract as extract_signals

log = get_logger("curriculum.graph")


class CurriculumGraphModule(Module):
    name = "curriculum.graph"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        # This module only acts pre-generation
        if ctx.response_text:
            return ModuleResult(data={})

        # Extract concepts the child mentioned
        signals = extract_signals(ctx.message)
        concept_ids = signals["concepts"]

        # Run semantic retrieval and graph lookup concurrently
        import asyncio
        rag_text, neighbours = await asyncio.gather(
            retrieve_semantic(ctx.message, ctx.subject, ctx.grade),
            get_concept_neighbourhood(ctx.db, concept_ids),
        )

        # Build curriculum context string
        parts = []
        if rag_text:
            parts.append(rag_text)
        if neighbours:
            prereqs = [n["label"] for n in neighbours if n["type"] == "prerequisite"]
            leads   = [n["label"] for n in neighbours if n["type"] == "leads-to"]
            if prereqs:
                parts.append(f"Prerequisites the child should know: {', '.join(prereqs)}")
            if leads:
                parts.append(f"This concept leads to: {', '.join(leads)}")

        curriculum_context = "\n\n".join(parts)

        log.debug(
            "curriculum_context_retrieved",
            concepts=concept_ids,
            rag_chars=len(rag_text),
            neighbours=len(neighbours),
        )

        return ModuleResult(data={
            "curriculum_context": curriculum_context,
            "concepts_detected": concept_ids,
        })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass  # curriculum graph holds no per-learner data
