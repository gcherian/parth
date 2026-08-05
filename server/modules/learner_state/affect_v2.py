"""
Persistence + per-turn wiring for Emotion Model v2 (emotion_engine.py).

emotion_engine.py is deliberately DB-free so it stays unit-testable in
isolation (see its own docstring and EMOTION_MODEL_V2_DESIGN.md). This
module is the thin, DB-touching bridge: load a learner's continuous
(valence, intensity) trajectory from learner_state.affect_state, fold one
turn's message into it via the engine, persist it back.

Deliberately independent of tutor_runtime/evaluator.py's LLM-based discrete
label — the appraisal impulse here comes only from the message text
(appraise_text), same as the design doc's "what's built now" scope.
Changing the evaluator prompt to emit control/value appraisal features
directly is flagged in EMOTION_MODEL_V2_DESIGN.md as a separate decision
(cost/latency tradeoff, needs an A/B pass) and is not done here.
"""
from __future__ import annotations

from modules.learner_state.emotion_engine import EmotionState, StudentEmotionEngine

# Small rolling window persisted alongside the point state — just enough for
# gear_shift's trajectory read (default window=3), cheap to store as JSONB.
HISTORY_WINDOW = 5


async def absorb_turn(conn, learner_id: str, message: str) -> dict:
    """Fold one turn's message into the learner's continuous emotion
    trajectory, persist it, and return the read-out (state + label +
    gear-shift) for the caller. Never raises — callers treat this as
    non-fatal, same as the other post-generation enrichment steps in
    learner_state/module.py."""
    row = await conn.fetchrow(
        "SELECT valence, intensity, affect_history "
        "FROM learner_state.affect_state WHERE learner_id=$1",
        learner_id,
    )
    if row and row["valence"] is not None:
        state = EmotionState(valence=row["valence"], intensity=row["intensity"])
        history = [EmotionState(valence=v, intensity=a) for v, a in (row["affect_history"] or [])]
    else:
        state = EmotionState()
        history = []
    if not history:
        history = [state]

    engine = StudentEmotionEngine(student_id=learner_id, state=state, history=history)
    engine.absorb_text(message)
    trimmed_history = engine.history[-HISTORY_WINDOW:]
    shift = engine.gear_shift()

    await conn.execute(
        """
        INSERT INTO learner_state.affect_state
            (learner_id, valence, intensity, affect_history, affect_gear_shift, updated_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (learner_id) DO UPDATE
        SET valence=$2, intensity=$3, affect_history=$4, affect_gear_shift=$5, updated_at=now()
        """,
        learner_id,
        engine.state.valence,
        engine.state.intensity,
        [[s.valence, s.intensity] for s in trimmed_history],
        shift,
    )

    return {
        "valence": engine.state.valence,
        "intensity": engine.state.intensity,
        "label": engine.label,
        "gear_shift": shift,
    }
