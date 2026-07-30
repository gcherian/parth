"""
learner.state — The growing portrait of this child.

Phase 1 (pre-generation): loads profile + builds learner context string for tutor.runtime.
Phase 3 (post-generation): updates knowledge, emotion, language, analogy scores,
                           and the psychological profile (psyche).
"""
import asyncio
from datetime import date

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from kernel.agent import AgentSignals
from kernel.agent_harness import AgentHarness
from foundation.observability import get_logger
from foundation.outbox import publish
from foundation import metrics as metrics_mod
from modules.learner_state import profile as prof
from modules.learner_state import knowledge as know
from modules.learner_state.signals import extract as extract_signals
from modules.learner_state import psyche as psy
from modules.learner_state import curiosity as cur
from modules.learner_state import episodes as epi
from modules.learner_state import open_loops as opl
from modules.learner_state.agents import build_agent_registry
from config import Config

log = get_logger("learner.state")

# Module-level harness — instantiated once, shared across all requests
_harness = AgentHarness(build_agent_registry())


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

            # ── Agent harness — live agents contribute their context slice ──
            agent_ctx, read_trace = await _harness.build_context_traced(conn, ctx.learner_id)
            if agent_ctx:
                learner_ctx = learner_ctx + "\n\n" + agent_ctx
            ctx.module_data["learner.state.read_trace"] = read_trace
            ctx.module_data["learner.state.context_assembled"] = learner_ctx

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
            except Exception as _puzzle_exc:
                log.debug("puzzle_portrait_skipped", error=str(_puzzle_exc))

            # ── Teacher portrait injection ─────────────────────────────────
            try:
                from modules.teacher.routes import get_teacher_portrait_context
                teacher_ctx = await get_teacher_portrait_context(conn, ctx.learner_id)
                if teacher_ctx:
                    learner_ctx = learner_ctx + "\n\n" + teacher_ctx
            except Exception as _teacher_exc:
                log.debug("teacher_portrait_skipped", error=str(_teacher_exc))

            return ModuleResult(data={
                "learner_context": learner_ctx,
                "profile": profile,
                "psyche": psyche,
            })

        else:
            # ── Phase 3: post-generation ───────────────────────────────────
            signals_raw = extract_signals(ctx.message)
            eval_result = await _evaluate(ctx.message, signals_raw["emotion_hint"])

            # Load current profile
            profile = await prof.get_or_create(conn, ctx.learner_id)

            # ── Build AgentSignals and dispatch to all agents ──────────────
            agent_signals = AgentSignals(
                learner_id=ctx.learner_id,
                session_id=ctx.session_id,
                phase="post",
                message=ctx.message,
                response_text=ctx.response_text,
                subject=ctx.subject,
                grade=ctx.grade,
                concepts=signals_raw.get("concepts", []),
                emotion=eval_result.get("emotion", "neutral"),
                engagement=float(eval_result.get("engagement", 5)),
                misconception=eval_result.get("misconception", ""),
                misconception_concept=eval_result.get("misconception_concept", ""),
                language_ratio=signals_raw.get("language_ratio", 1.0),
                total_questions=profile.get("total_questions", 0),
                prev_domains=ctx.module_data.get("tutor.runtime", {}).get("response_domains", []),
                profile=dict(profile),
                eval_result=eval_result,
            )
            dispatch_trace = await _harness.dispatch(agent_signals, conn)
            ctx.module_data["learner.state.dispatch_trace"] = dispatch_trace
            ctx.module_data["learner.state.agent_signals"] = {
                "emotion":    agent_signals.emotion,
                "engagement": agent_signals.engagement,
                "concepts":   agent_signals.concepts,
                "misconception": agent_signals.misconception,
                "language_ratio": agent_signals.language_ratio,
                "events":     dict(agent_signals.events),
            }

            # Convenience aliases (used below)
            misconception = agent_signals.misconception
            misc_concept  = agent_signals.misconception_concept
            emotion       = agent_signals.emotion
            engagement    = agent_signals.engagement

            # ── record_question (not in harness — needs module-level context) ──
            await prof.record_question(conn, ctx.learner_id)

            # ── Log interaction ────────────────────────────────────────────
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

            # ── Weak concepts → publish learner.struggling ─────────────────
            weak = await know.weak_concepts(conn, ctx.learner_id)
            if len(weak) >= 3:
                await publish(
                    conn, "learner.struggling",
                    {"learner_id": ctx.learner_id, "weak_concepts": weak},
                    aggregate="learner", aggregate_id=ctx.learner_id,
                )

            # ── Pilot metrics (fire-and-forget, never block) ───────────────
            try:
                await metrics_mod.record_pretest_baseline(conn, ctx.learner_id)
                await metrics_mod.record_interaction(
                    conn,
                    learner_id=ctx.learner_id,
                    session_date=date.today(),
                    concepts=signals_raw.get("concepts", []),
                    had_misconception=bool(misconception and misc_concept),
                    harmful=False,
                )
            except Exception as _m_exc:
                log.warning("metrics_fire_forget_failed", error=str(_m_exc))

            # ── Trigger Krishna Oracle asynchronously ──────────────────────
            total_q = profile.get("total_questions", 0) + 1
            should_consult_krishna = (
                Config.ANTHROPIC_API_KEY and
                total_q > 0 and
                total_q % Config.KRISHNA_INTERVAL == 0
            )
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

            # Read back updated psyche for return value
            updated_psyche = await psy.get_psyche(conn, ctx.learner_id)
            log.debug(
                "psyche_updated",
                learner_id=ctx.learner_id,
                sample_count=updated_psyche["sample_count"],
            )

            return ModuleResult(data={
                "emotion":       emotion,
                "engagement":    engagement,
                "misconception": misconception,
                "psyche":        updated_psyche,
            })

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        conn = ctx.db
        for table in [
            # core
            "learner_state.profiles",
            "learner_state.knowledge",
            "learner_state.misconception_map",
            "learner_state.emotion_history",
            "learner_state.interactions",
            "learner_state.psyche",
            "learner_state.confidence_calibration",
            # memory
            "learner_state.episodes",
            "learner_state.curiosity_sessions",
            "learner_state.open_loops",
            # agent harness tables
            "learner_state.affect_state",
            "learner_state.curriculum_map",
            "learner_state.challenge_state",
            "learner_state.analogy_history",
            "learner_state.language_state",
            "learner_state.register_state",
            "learner_state.delight_state",
            "learner_state.inquiry_state",
            "learner_state.family_context",
            "learner_state.rhythm_state",
            "learner_state.pattern_state",
            "learner_state.kt_events",
            "learner_state.learning_velocity_state",
            "learner_state.motivation_drive_state",
            "learner_state.social_learning_state",
            "learner_state.value_purpose_reflections",
            "learner_state.value_purpose_state",
            "learner_state.dimension_snapshots",
            # practice engine
            "practice_engine.cards",
            "practice_engine.answers",
        ]:
            await conn.execute(
                f"DELETE FROM {table} WHERE learner_id = $1", learner_id
            )
        log.info("learner_state_erased", learner_id=learner_id)
