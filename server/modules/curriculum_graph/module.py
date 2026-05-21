"""
curriculum.graph — Concept graph + NCERT RAG retrieval.

Phase 1 (pre-generation): retrieves semantic context, concept neighbourhood,
next recommended concept (graph-driven), and misconception remediations.
"""
import asyncio

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from modules.curriculum_graph.graph import (
    retrieve_semantic,
    get_concept_neighbourhood,
    get_next_concept,
    get_remediation,
)
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
        rag_text, neighbours, next_concept = await asyncio.gather(
            retrieve_semantic(ctx.message, ctx.subject, ctx.grade),
            get_concept_neighbourhood(ctx.db, concept_ids),
            get_next_concept(ctx.db, ctx.learner_id, ctx.grade, ctx.subject),
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

        # Append next-concept recommendation only if the learner hasn't already
        # mentioned it in their message
        next_concept_id = None
        if next_concept:
            next_concept_id = next_concept["concept_id"]
            mentioned_ids = set(concept_ids)
            if next_concept_id not in mentioned_ids:
                parts.append(
                    f"Next recommended concept: {next_concept['label']} — "
                    f"{next_concept['reason']}"
                )

        # Append remediation hint if a misconception was flagged in a prior turn
        remediation_data = None
        prior_misconception = ctx.module_data.get("misconception_concept")
        if prior_misconception:
            misconception_text = ctx.module_data.get("misconception_text", ctx.message)
            remediation_data = await get_remediation(
                ctx.db, prior_misconception, misconception_text
            )
            if remediation_data:
                parts.append(
                    f"Remediation hint for {prior_misconception}: "
                    f"{remediation_data['remediation_text']}"
                )
                if remediation_data.get("analogy_hint"):
                    parts.append(f"Analogy: {remediation_data['analogy_hint']}")

        curriculum_context = "\n\n".join(parts)

        log.debug(
            "curriculum_context_retrieved",
            concepts=concept_ids,
            rag_chars=len(rag_text),
            neighbours=len(neighbours),
            next_concept=next_concept_id,
            remediation=bool(remediation_data),
        )

        return ModuleResult(data={
            "curriculum_context": curriculum_context,
            "concepts_detected": concept_ids,
            "next_concept": next_concept,
        })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass  # curriculum graph holds no per-learner data
