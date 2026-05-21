"""
practice.engine — SM-2 spaced repetition + question scheduling.

Phase 3 (post-generation): logs the interaction concept exposure and schedules
next review. Detects when a child is ready to advance (p_mastery threshold).
"""
from datetime import datetime, timedelta

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from foundation.outbox import publish
from modules.practice_engine.sm2 import update_card, quality_from_correct

log = get_logger("practice.engine")

_MASTERY_ADVANCE_THRESHOLD = 0.75


class PracticeEngineModule(Module):
    name = "practice.engine"
    handles = ["interaction.requested", "practice.session_requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        # Only act post-generation
        if not ctx.response_text:
            return ModuleResult(data={})

        conn = ctx.db
        concepts = ctx.module_data.get("curriculum.graph", {}).get("concepts_detected", [])
        if not concepts:
            return ModuleResult(data={})

        # Get misconception signal from learner.state post-processing
        misconception = ctx.module_data.get("learner.state", {}).get("misconception", "")

        for concept_id in concepts[:3]:  # cap at 3 concepts per interaction
            # Load or create the SM-2 card
            card = await conn.fetchrow(
                """
                SELECT repetitions, interval_days, ease_factor
                FROM practice_engine.cards
                WHERE learner_id = $1 AND concept_id = $2
                """,
                ctx.learner_id, concept_id,
            )

            if card is None:
                reps, interval, ef = 0, 1.0, 2.5
            else:
                reps, interval, ef = card["repetitions"], card["interval_days"], card["ease_factor"]

            correct = not bool(misconception)
            quality = quality_from_correct(correct)

            new_reps, new_interval, new_ef = update_card(reps, interval, ef, quality)
            next_review = datetime.utcnow() + timedelta(days=new_interval)

            # Upsert the card
            await conn.execute(
                """
                INSERT INTO practice_engine.cards
                    (learner_id, concept_id, next_review, interval_days, ease_factor, repetitions)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (learner_id, concept_id) DO UPDATE
                SET next_review   = EXCLUDED.next_review,
                    interval_days = EXCLUDED.interval_days,
                    ease_factor   = EXCLUDED.ease_factor,
                    repetitions   = EXCLUDED.repetitions
                """,
                ctx.learner_id, concept_id, next_review, new_interval, new_ef, new_reps,
            )

            # Record answer
            await conn.execute(
                """
                INSERT INTO practice_engine.answers
                    (learner_id, concept_id, correct, quality)
                VALUES ($1, $2, $3, $4)
                """,
                ctx.learner_id, concept_id, correct, quality,
            )

            # Check if mastery threshold crossed
            knowledge_row = await conn.fetchrow(
                "SELECT p_mastery FROM learner_state.knowledge WHERE learner_id=$1 AND concept_id=$2",
                ctx.learner_id, concept_id,
            )
            if knowledge_row and knowledge_row["p_mastery"] >= _MASTERY_ADVANCE_THRESHOLD:
                await publish(
                    conn, "practice.concept_cleared",
                    {"learner_id": ctx.learner_id, "concept_id": concept_id,
                     "p_mastery": knowledge_row["p_mastery"]},
                    aggregate="learner", aggregate_id=ctx.learner_id,
                )
                log.info("concept_cleared", learner_id=ctx.learner_id, concept=concept_id)

        return ModuleResult(data={"practice_scheduled": concepts})

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        conn = ctx.db
        await conn.execute("DELETE FROM practice_engine.cards WHERE learner_id = $1", learner_id)
        await conn.execute("DELETE FROM practice_engine.answers WHERE learner_id = $1", learner_id)
        log.info("practice_engine_erased", learner_id=learner_id)
