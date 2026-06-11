"""Humor & Delight Guide — safe levity and warmth.

No sarcasm, ridicule, identity humor, or humor during distress.
"""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals

_DELIGHT_MARKERS = {"oh wow", "no way", "insane", "crazy", "that's wild", "amazing", "so cool"}
_NOGO_DEFAULTS   = ["identity", "religion", "family", "appearance", "caste"]


class HumorDelightGuideAgent(LearnerAgent):
    name = "humor_delight_guide"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            msg_lower   = signals.message.lower()
            humor_landed = any(t in msg_lower for t in _DELIGHT_MARKERS)
            distress     = signals.events.get("distress.detected", False)

            row = await conn.fetchrow(
                "SELECT humor_tolerance, delight_triggers FROM learner_state.delight_state WHERE learner_id=$1",
                signals.learner_id,
            )
            tolerance = (row["humor_tolerance"] if row else 0.5) or 0.5
            triggers  = json.loads(row["delight_triggers"] if row else "[]") if row else []

            tolerance = min(1.0, tolerance + 0.05) if humor_landed else tolerance
            tolerance = max(0.1, tolerance - 0.1) if distress else tolerance

            if humor_landed and signals.concepts:
                concept = signals.concepts[0]
                if concept not in triggers:
                    triggers.append(concept)

            await conn.execute(
                """INSERT INTO learner_state.delight_state
                   (learner_id, humor_tolerance, delight_triggers, nogo_zones, updated_at)
                   VALUES ($1,$2,$3,$4,now())
                   ON CONFLICT (learner_id) DO UPDATE
                   SET humor_tolerance=$2, delight_triggers=$3, updated_at=now()""",
                signals.learner_id, tolerance,
                json.dumps(triggers[:10]), json.dumps(_NOGO_DEFAULTS),
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {"delight.approved": not signals.events.get("distress.detected", False)}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT humor_tolerance FROM learner_state.delight_state WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return ""
            t = row["humor_tolerance"] or 0.5
            if t < 0.3:
                return "Humor: off — child prefers focused help right now."
            if t > 0.7:
                return "Delight: high — playful riddles, light pattern jokes welcome."
            return "Humor: occasional warmth OK; read the room."
        except Exception:
            return ""
