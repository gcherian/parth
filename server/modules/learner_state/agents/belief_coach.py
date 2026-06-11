"""Belief Coach — self-efficacy, calibration, metacognition. Sole psyche writer.

No empty praise, no shaming, no fixed-ability language.
Ref: Dweck (growth mindset); CASEL (metacognition as SEL competence).
"""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import psyche as psy
from modules.learner_state.signals import extract as extract_signals

_OVERCONFIDENCE = {"i know", "easy", "obviously", "already know", "pata hai", "aata hai", "simple"}
_UNDERCONFIDENCE = {"i can't", "too hard", "give up", "nahi aata", "samajh nahi", "never get"}


class BeliefCoachAgent(LearnerAgent):
    name = "belief_coach"
    phase = "both"
    memory_window = "month"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            raw = extract_signals(signals.message)
            psych_signals = psy.extract_psyche_signals(
                message=signals.message,
                signals=raw,
                eval_result=signals.eval_result,
                profile=signals.profile,
            )
            await psy.update_psyche(conn, signals.learner_id, psych_signals)

            # Confidence calibration against actual mastery
            msg_lower = signals.message.lower()
            stated_high = any(w in msg_lower for w in _OVERCONFIDENCE)
            if stated_high and signals.concepts:
                concept_id = signals.concepts[0]
                mastery = await conn.fetchval(
                    "SELECT p_mastery FROM learner_state.knowledge WHERE learner_id=$1 AND concept_id=$2",
                    signals.learner_id, concept_id,
                )
                actual = float(mastery or 0.05)
                gap = round(0.9 - actual, 3)
                await conn.execute(
                    """INSERT INTO learner_state.confidence_calibration
                       (learner_id, concept_id, stated_high, actual_mastery, gap, updated_at)
                       VALUES ($1,$2,$3,$4,$5,now())
                       ON CONFLICT (learner_id, concept_id) DO UPDATE
                       SET stated_high=$3, actual_mastery=$4, gap=$5, updated_at=now()""",
                    signals.learner_id, concept_id, stated_high, actual, gap,
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        msg_lower = signals.message.lower()
        if any(w in msg_lower for w in _OVERCONFIDENCE):
            return {"confidence.bias": "over"}
        if any(w in msg_lower for w in _UNDERCONFIDENCE):
            return {"confidence.bias": "under"}
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            psyche = await psy.get_psyche(conn, learner_id)
            if psyche.get("sample_count", 0) < 3:
                return ""
            growth  = psyche.get("growth_mindset", 0.5)
            anxiety = psyche.get("anxiety", 0.5)
            depth   = psyche.get("depth_preference", 0.5)
            mindset = "growth" if growth >= 0.6 else ("fixed" if growth <= 0.35 else "mixed")
            style   = "conceptual" if depth >= 0.6 else ("procedural" if depth <= 0.35 else "balanced")
            return (
                f"Mindset: {mindset} (growth={growth:.2f}). Anxiety={anxiety:.2f}. Style: {style}. "
                "[Reframe errors as data; no ability labels; no empty praise.]"
            )
        except Exception:
            return ""
