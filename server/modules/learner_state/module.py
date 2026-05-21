"""
learner.state — The growing portrait of this child.

Phase 1 (pre-generation): loads profile + builds learner context string for tutor.runtime.
Phase 3 (post-generation): updates knowledge, emotion, language, analogy scores,
                           and the psychological profile (psyche).
"""
import asyncio

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from foundation.outbox import publish
from modules.learner_state import profile as prof
from modules.learner_state import knowledge as know
from modules.learner_state.signals import extract as extract_signals
from modules.learner_state import psyche as psy
from config import Config

log = get_logger("learner.state")


async def _consult_krishna(learner_id: str, trigger: str):
    """Background task — opens its own DB connection so it doesn't block the request."""
    try:
        from foundation.db import get_pool
        from modules.krishna_oracle.oracle import consult
        pool = await get_pool()
        async with pool.acquire() as conn:
            await consult(conn, learner_id, trigger)
    except Exception as e:
        log.warning("krishna_background_failed", learner_id=learner_id, error=str(e))


async def _evaluate(question: str, emotion_hint: str) -> dict:
    from modules.tutor_runtime.evaluator import evaluate
    return await evaluate(question, emotion_hint)


class LearnerStateModule(Module):
    name = "learner.state"
    handles = ["interaction.requested", "interaction.completed"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        conn = ctx.db

        if not ctx.response_text:
            # ── Phase 1: pre-generation ────────────────────────────────────
            profile = await prof.get_or_create(
                conn, ctx.learner_id,
                name=event.payload.get("learner_name", ""),
                grade=ctx.grade,
            )
            # Load psyche profile for prompt injection
            psyche = await psy.get_psyche(conn, ctx.learner_id)
            learner_ctx = await prof.build_learner_context(
                conn, ctx.learner_id, profile, psyche
            )

            # ── Puzzle portrait injection ─────────────────────────────────
            # If the child has done any puzzles, append their portrait context
            # to the learner_context string so Parth knows their register + telos.
            try:
                from modules.puzzle_engine.module import _load_portrait, _load_register_state
                from modules.puzzle_engine.portrait import build_portrait_context
                from modules.puzzle_engine.register import RegisterState, dominant_register
                portrait = await _load_portrait(conn, ctx.learner_id, ctx.grade)
                if portrait.get("confidence", 0.0) >= 0.20:
                    portrait_ctx = build_portrait_context(portrait, psyche)
                    if portrait_ctx:
                        learner_ctx = learner_ctx + "\n\n" + portrait_ctx
                    # Update register from current chat message (chat also reveals domain language)
                    reg_raw = await _load_register_state(conn, ctx.learner_id)
                    from modules.puzzle_engine.register import RegisterState, update as update_reg
                    reg = RegisterState(
                        learner_id=ctx.learner_id,
                        probs=reg_raw.get("probs", {}),
                        n_messages=reg_raw.get("n_messages", 0),
                    )
                    reg = update_reg(reg, ctx.message)
                    # Persist updated register state
                    import json as _rjson
                    await conn.execute("""
                        INSERT INTO puzzle_engine.register_states (learner_id, state_json, updated_at)
                        VALUES ($1, $2, now())
                        ON CONFLICT (learner_id) DO UPDATE
                        SET state_json=$2, updated_at=now()
                    """, ctx.learner_id, _rjson.dumps({
                        "probs": reg.probs,
                        "n_messages": reg.n_messages,
                        "dominant_question_type": reg.dominant_question_type,
                        "avg_sentence_length": reg.avg_sentence_length,
                    }))
            except Exception:
                pass   # puzzle engine not yet active — silent fallback

            return ModuleResult(data={
                "learner_context": learner_ctx,
                "profile": profile,
                "psyche": psyche,
            })

        else:
            # ── Phase 3: post-generation ───────────────────────────────────
            signals     = extract_signals(ctx.message)
            eval_result = await _evaluate(ctx.message, signals["emotion_hint"])

            misconception = eval_result.get("misconception", "")
            misc_concept  = eval_result.get("misconception_concept", "")
            emotion       = eval_result.get("emotion", "neutral")
            engagement    = float(eval_result.get("engagement", 5))

            # Load current profile for psyche signal extraction
            profile = await prof.get_or_create(conn, ctx.learner_id)

            # Knowledge state updates
            if signals["concepts"]:
                await know.record_exposure(conn, ctx.learner_id, signals["concepts"])
            if misconception and misc_concept:
                await know.record_misconception(conn, ctx.learner_id, [misc_concept])
            if not misconception and signals["concepts"]:
                await know.record_demonstration(conn, ctx.learner_id, signals["concepts"])

            # Profile updates
            if misconception and misc_concept:
                await prof.update_misconception_map(conn, ctx.learner_id, misc_concept, misconception)
            await prof.update_emotion(conn, ctx.learner_id, emotion, engagement)
            await prof.update_language(conn, ctx.learner_id, signals["language_ratio"])
            await prof.update_motivational_profile(conn, ctx.learner_id, ctx.subject, engagement)
            await prof.record_question(conn, ctx.learner_id)

            # Analogy lag-attribution
            prev_domains = ctx.module_data.get("tutor.runtime", {}).get("response_domains", [])
            if prev_domains:
                await prof.update_analogy_scores(conn, ctx.learner_id, prev_domains, engagement)

            # ── Psyche update (runs every interaction) ─────────────────────
            psych_signals = psy.extract_psyche_signals(
                message=ctx.message,
                signals=signals,
                eval_result=eval_result,
                profile=profile,
            )
            updated_psyche = await psy.update_psyche(conn, ctx.learner_id, psych_signals)
            log.debug(
                "psyche_updated",
                learner_id=ctx.learner_id,
                sample_count=updated_psyche["sample_count"],
                **{k: v for k, v in updated_psyche.items()
                   if k not in ("sample_count", "learner_id")},
            )

            # Log interaction
            await conn.execute(
                """
                INSERT INTO learner_state.interactions
                    (learner_id, request_id, subject, grade, question, response,
                     model, duration_ms, misconception, emotion, engagement)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                ctx.learner_id, ctx.request_id, ctx.subject, ctx.grade,
                ctx.message[:1000], ctx.response_text[:2000],
                ctx.model_used, 0,
                misconception, emotion, engagement,
            )

            # Emit events for downstream modules
            weak = await know.weak_concepts(conn, ctx.learner_id)
            if len(weak) >= 3:
                await publish(
                    conn, "learner.struggling",
                    {"learner_id": ctx.learner_id, "weak_concepts": weak},
                    aggregate="learner", aggregate_id=ctx.learner_id,
                )

            # ── Trigger Krishna Oracle asynchronously ──────────────────────
            # Periodic: every KRISHNA_INTERVAL interactions
            total_q = profile.get("total_questions", 0) + 1
            should_consult_krishna = (
                Config.ANTHROPIC_API_KEY and
                total_q > 0 and
                total_q % Config.KRISHNA_INTERVAL == 0
            )
            # Also trigger on 3rd+ occurrence of same misconception
            if not should_consult_krishna and misconception and misc_concept:
                misc_count = await conn.fetchval(
                    "SELECT count FROM learner_state.misconception_map "
                    "WHERE learner_id=$1 AND concept_id=$2 AND misconception=$3",
                    ctx.learner_id, misc_concept, misconception,
                )
                should_consult_krishna = Config.ANTHROPIC_API_KEY and (misc_count or 0) >= 3

            if should_consult_krishna:
                trigger = "periodic" if total_q % Config.KRISHNA_INTERVAL == 0 else "misconception"
                asyncio.create_task(_consult_krishna(ctx.learner_id, trigger))
                log.info("krishna_triggered", learner_id=ctx.learner_id, trigger=trigger)

            return ModuleResult(data={
                "emotion":     emotion,
                "engagement":  engagement,
                "misconception": misconception,
                "psyche":      updated_psyche,
            })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        conn = ctx.db
        for table in [
            "learner_state.profiles",
            "learner_state.knowledge",
            "learner_state.misconception_map",
            "learner_state.emotion_history",
            "learner_state.interactions",
            "learner_state.psyche",
        ]:
            await conn.execute(
                f"DELETE FROM {table} WHERE learner_id = $1", learner_id
            )
        log.info("learner_state_erased", learner_id=learner_id)
