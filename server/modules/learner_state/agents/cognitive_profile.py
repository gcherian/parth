"""Agent 03 — Cognitive Profile: infers psyche dimensions from conversation."""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import psyche as psy
from modules.learner_state.signals import extract as extract_signals


class CognitiveProfileAgent(LearnerAgent):
    name = "cognitive_profile"
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
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            psyche = await psy.get_psyche(conn, learner_id)
            if psyche.get("sample_count", 0) < 3:
                return ""
            depth  = psyche.get("depth_preference", 0.5)
            consc  = psyche.get("conscientiousness", 0.5)
            style  = "conceptual deep" if depth >= 0.6 else ("procedural" if depth <= 0.35 else "balanced")
            struct = "structured" if consc >= 0.6 else ("flexible" if consc <= 0.35 else "moderate")
            return (
                f"Thinking style: {style} (depth={depth:.2f}), {struct} (consc={consc:.2f})."
            )
        except Exception:
            return ""
