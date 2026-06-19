"""Register Tuner — tone, sentence length, formality, vocabulary level.

No manipulative mimicry; age-appropriate, respectful voice.
"""
from __future__ import annotations
from typing import Any
from kernel.agent import BaseAgent, AgentSignals

_CASUAL_WORDS = {"yaar", "yeh", "kya", "toh", "bhai", "okay", "cool", "wait", "so", "like", "dude"}


def _sentence_length(text: str) -> str:
    words = len(text.split())
    if words < 8:
        return "short"
    if words < 20:
        return "medium"
    return "long"


def _formality(text: str) -> float:
    words = text.lower().split()
    casual_ratio = sum(1 for w in words if w in _CASUAL_WORDS) / max(len(words), 1)
    return round(max(0.0, min(1.0, 1.0 - casual_ratio * 4)), 2)


class RegisterTunerAgent(BaseAgent):
    name = "register_tuner"
    phase = "both"
    memory_window = "permanent"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        pref_len  = _sentence_length(signals.message)
        formality = _formality(signals.message)
        await conn.execute(
            """INSERT INTO learner_state.register_state
               (learner_id, sentence_length_pref, formality, updated_at)
               VALUES ($1,$2,$3,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET sentence_length_pref = CASE
                     WHEN register_state.sentence_length_pref = $2 THEN $2
                     ELSE 'medium'
                   END,
               formality = (register_state.formality * 0.7 + $3 * 0.3),
               updated_at = now()""",
            signals.learner_id, pref_len, formality,
        )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {"register.profile": {
            "sentence_length": _sentence_length(signals.message),
            "formality": _formality(signals.message),
        }}

    async def _read(self, conn, learner_id: str) -> str:
        row = await conn.fetchrow(
            "SELECT sentence_length_pref, formality FROM learner_state.register_state WHERE learner_id=$1",
            learner_id,
        )
        if not row:
            return ""
        length    = row["sentence_length_pref"] or "medium"
        formality = row["formality"] or 0.5
        tone = "formal" if formality > 0.65 else ("conversational" if formality > 0.35 else "casual")
        return f"Register: {tone} tone, {length} sentences. Match this phrasing."
