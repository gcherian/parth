"""Agent 15 — Analogy Domain: tracks which analogies land best."""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof

_RETIREMENT_SCORE  = 0.70
_RETIREMENT_MASTERY = 3
_MASTERY_THRESHOLD  = 0.72


class AnalogyDomainAgent(LearnerAgent):
    name = "analogy_domain"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            if signals.prev_domains:
                await prof.update_analogy_scores(
                    conn, signals.learner_id, signals.prev_domains, signals.engagement
                )
            # Metaphor retirement check
            row = await conn.fetchrow(
                "SELECT analogy_scores FROM learner_state.profiles WHERE learner_id=$1",
                signals.learner_id,
            )
            if not row:
                return
            scores: dict = row["analogy_scores"] or {}
            if isinstance(scores, str):
                scores = json.loads(scores)
            if not scores:
                return
            mastered_count = await conn.fetchval(
                "SELECT COUNT(*) FROM learner_state.knowledge WHERE learner_id=$1 AND p_mastery>$2",
                signals.learner_id, _MASTERY_THRESHOLD,
            )
            top_domain = max(scores, key=lambda k: scores[k])
            if (mastered_count or 0) >= _RETIREMENT_MASTERY and scores[top_domain] > _RETIREMENT_SCORE:
                # Mark retired — set score to 0 so it drops from active
                scores[top_domain] = 0.0
                await conn.execute(
                    "UPDATE learner_state.profiles SET analogy_scores=$2 WHERE learner_id=$1",
                    signals.learner_id, json.dumps(scores),
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT analogy_scores FROM learner_state.profiles WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                return ""
            scores: dict = row["analogy_scores"] or {}
            if isinstance(scores, str):
                scores = json.loads(scores)
            active = {d: s for d, s in scores.items() if s > 0}
            if not active:
                return ""
            top_domain = max(active, key=lambda k: active[k])
            top_score  = active[top_domain]
            return f"Analogies: {top_domain} lands (score={top_score:.2f})."
        except Exception:
            return ""
