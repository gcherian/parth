"""Family Alliance — caregiver context, consent-gated.

Consent-gated; surface uncertainty; protect child dignity and privacy.
Ref: CASEL Framework — family and caregiver partnership extends learning beyond session.
"""
from __future__ import annotations
import json
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals


class FamilyAllianceAgent(LearnerAgent):
    name = "family_alliance"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await conn.execute(
                """INSERT INTO learner_state.family_context
                   (learner_id, consent_level, updated_at)
                   VALUES ($1, 1, now())
                   ON CONFLICT (learner_id) DO NOTHING""",
                signals.learner_id,
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT consent_level, caregiver_lang, home_supports "
                "FROM learner_state.family_context WHERE learner_id=$1",
                learner_id,
            )
            if not row or (row["consent_level"] or 1) < 2:
                return ""  # caregiver onboarding not yet done
            parts = []
            if row["caregiver_lang"]:
                parts.append(f"Home language: {row['caregiver_lang']}.")
            if row["home_supports"]:
                supports = json.loads(row["home_supports"] or "{}")
                if supports:
                    items = ", ".join(f"{k}={v}" for k, v in list(supports.items())[:2])
                    parts.append(f"Home context: {items}.")
            return " ".join(parts)
        except Exception:
            return ""
