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

            # ── Curiosity tracker injection ───────────────────────────────
            try:
                threads = await cur.load(conn, ctx.learner_id, ctx.session_id)
                curiosity_ctx = cur.build_curiosity_context(threads)
                if curiosity_ctx:
                    learner_ctx = learner_ctx + "\n\n" + curiosity_ctx
            except Exception:
                pass   # never block generation on curiosity tracker

            # ── Episodic memory injection ─────────────────────────────────
            try:
                episode_list = await epi.load_for_prompt(conn, ctx.learner_id)
                episode_ctx  = epi.build_episode_context(episode_list)
                if episode_ctx:
                    learner_ctx = learner_ctx + "\n\n" + episode_ctx
            except Exception:
                pass   # never block generation on episodic memory

            # ── Open-loop injection ───────────────────────────────────────
            try:
                await opl.expire_old(conn, ctx.learner_id)
                loops = await opl.load_open(conn, ctx.learner_id)
                loop_ctx = opl.build_context(loops)
                if loop_ctx:
                    learner_ctx = learner_ctx + "\n\n" + loop_ctx
            except Exception:
                pass   # never block generation on open loops

            return ModuleResult(data={
                "learner_context": learner_ctx,
                "profile": profile,
                "psyche": psyche,
            })

        else:
            # ── Phase 3: post-generation ───────────────────────────────────
            signals     = extract_signals(ctx.message)
            eval_result = await _evaluate(ctx.message, signals["emotion_hint"])

            # ── Episodic memory — detect and store meaningful moments ─────
            try:
                ep_type = epi.detect_type(ctx.message)
                if ep_type:
                    sig      = extract_signals(ctx.message)
                    concepts = sig["concepts"]
                    patterns = await epi.get_patterns_for_message(conn, concepts)
                    await epi.store(conn, ctx.learner_id, ep_type,
                                    ctx.message, concepts, patterns)
            except Exception as e:
                log.warning("episode_store_failed", error=str(e))

            # ── Curiosity tracker update ───────────────────────────────────
            cur_threads: list = []
            try:
                recent_kws = await cur.get_recent_keywords(conn, ctx.learner_id, ctx.session_id)
                signal     = cur.detect_signal(ctx.message, recent_kws)
                cur_threads = await cur.load(conn, ctx.learner_id, ctx.session_id)
                cur_threads = cur.update_threads(cur_threads, signal, ctx.message)
                await cur.save(conn, ctx.learner_id, ctx.session_id, cur_threads)
                if signal["type"] != "none":
                    log.debug("curiosity_signal", learner_id=ctx.learner_id,
                              type=signal["type"], heat_delta=signal["heat_delta"])
            except Exception as e:
                log.warning("curiosity_update_failed", error=str(e))

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
                await know.record_misconception(
                    conn, ctx.learner_id, [misc_concept], session_id=ctx.session_id
                )
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

            # ── Open-loop generation ───────────────────────────────────────
            try:
                ep_type_for_loop = epi.detect_type(ctx.message)
                total_q = profile.get("total_questions", 0) + 1
                if opl.should_generate(total_q, ep_type_for_loop):
                    recent_episodes = await epi.load_for_prompt(conn, ctx.learner_id)
                    q_text, q_concepts = opl.generate(
                        concepts=signals.get("concepts", []),
                        episodes=recent_episodes,
                        threads=cur_threads,
                    )
                    if q_text:
                        await opl.store(conn, ctx.learner_id, q_text,
                                        q_concepts or signals.get("concepts", []))
                        log.debug("open_loop_generated", learner_id=ctx.learner_id,
                                  question=q_text[:60])
            except Exception as e:
                log.warning("open_loop_generate_failed", error=str(e))

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

            # ── Pilot metrics (fire-and-forget, never block) ───────────────
            try:
                await metrics_mod.record_interaction(
                    conn,
                    learner_id=ctx.learner_id,
                    session_date=date.today(),
                    concepts=signals.get("concepts", []),
                    had_misconception=bool(misconception and misc_concept),
                    harmful=False,
                )
            except Exception as _m_exc:
                log.warning("metrics_fire_forget_failed", error=str(_m_exc))

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
            "learner_state.episodes",
            "learner_state.curiosity_sessions",
            "learner_state.open_loops",
        ]:
            await conn.execute(
                f"DELETE FROM {table} WHERE learner_id = $1", learner_id
            )
        log.info("learner_state_erased", learner_id=learner_id)
