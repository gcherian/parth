"""Transfer Weaver — analogies, near/far transfer, cross-domain bridges.

Clearly separate analogy from literal truth; retire analogies once concept is mastered.
"""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof

_RETIREMENT_SCORE   = 0.70
_RETIREMENT_MASTERY = 3
_MASTERY_THRESHOLD  = 0.72


class TransferWeaverAgent(LearnerAgent):
    name = "transfer_weaver"
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
                for domain in signals.prev_domains:
                    await conn.execute(
                        """INSERT INTO learner_state.analogy_history
                           (learner_id, domain, worked, concept_id, created_at)
                           VALUES ($1,$2,$3,$4,now())""",
                        signals.learner_id, domain,
                        signals.engagement > 6.0,
                        signals.concepts[0] if signals.concepts else "",
                    )

            # Metaphor retirement: when concept is mastered, zero out its leading analogy
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
            mastered = await conn.fetchval(
                "SELECT COUNT(*) FROM learner_state.knowledge WHERE learner_id=$1 AND p_mastery>$2",
                signals.learner_id, _MASTERY_THRESHOLD,
            )
            top = max(scores, key=lambda k: scores[k])
            if (mastered or 0) >= _RETIREMENT_MASTERY and scores[top] > _RETIREMENT_SCORE:
                scores[top] = 0.0
                await conn.execute(
                    "UPDATE learner_state.profiles SET analogy_scores=$2 WHERE learner_id=$1",
                    signals.learner_id, json.dumps(scores),
                )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        if signals.prev_domains:
            return {"analogy.suggested": signals.prev_domains[0]}
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT analogy_scores FROM learner_state.profiles WHERE learner_id=$1", learner_id
            )
            if not row:
                return ""
            scores: dict = row["analogy_scores"] or {}
            if isinstance(scores, str):
                scores = json.loads(scores)
            active = {d: s for d, s in scores.items() if s > 0}
            if not active:
                return ""
            top = max(active, key=active.get)
            failed = await conn.fetch(
                "SELECT DISTINCT domain FROM learner_state.analogy_history "
                "WHERE learner_id=$1 AND worked=false ORDER BY created_at DESC LIMIT 2",
                learner_id,
            )
            parts = [f"Analogy anchor: {top} (score={active[top]:.2f})."]
            if failed:
                parts.append("Avoid: " + ", ".join(r["domain"] for r in failed) + ".")
            parts.append("Label analogies as analogies; separate metaphor from literal truth.")
            return " ".join(parts)
        except Exception:
            return ""
