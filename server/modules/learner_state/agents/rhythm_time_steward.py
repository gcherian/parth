"""Rhythm & Time Steward — peak-focus window, session pacing, fatigue signals.

Never optimize against sleep, wellbeing, or family rhythms.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from kernel.agent import BaseAgent, AgentSignals


class RhythmTimeStewardAgent(BaseAgent):
    name = "rhythm_time_steward"
    phase = "both"
    memory_window = "permanent"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        hour = datetime.utcnow().hour
        row  = await conn.fetchrow(
            "SELECT peak_hour, session_count_today FROM learner_state.rhythm_state WHERE learner_id=$1",
            signals.learner_id,
        )
        peak  = (row["peak_hour"] if row else hour) or hour
        count = (row["session_count_today"] if row else 0) or 0

        if signals.engagement > 6.5:
            peak = round(peak * 0.8 + hour * 0.2)  # exponential blend toward high-engagement hour

        await conn.execute(
            """INSERT INTO learner_state.rhythm_state
               (learner_id, peak_hour, session_count_today, last_session_quality, updated_at)
               VALUES ($1,$2,$3,$4,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET peak_hour = $2,
                   session_count_today = CASE
                     WHEN date_trunc('day', rhythm_state.updated_at) = date_trunc('day', now())
                     THEN rhythm_state.session_count_today + 1
                     ELSE 1
                   END,
               last_session_quality = $4,
               updated_at = now()""",
            signals.learner_id, peak, count + 1, signals.engagement,
        )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        from modules.learner_state.chrono_ritual import get_effective_schedule, get_inferred_window

        inferred = await get_inferred_window(conn, learner_id)
        if not inferred["has_signal"]:
            return ""
        count = inferred["session_count_today"]
        qual  = inferred["last_session_quality"] if inferred["last_session_quality"] is not None else 5.0
        if count > 3:
            return f"Pacing: {count} sessions today — consider a break before continuing."

        schedule = await get_effective_schedule(conn, learner_id)
        hour = schedule["hour"]
        if schedule["source"] == "confirmed_appointment":
            return f"Rhythm: confirmed session time ~{hour:02d}:00 (parent-set). Last quality={qual:.1f}/10."
        return f"Rhythm: peak focus ~{hour:02d}:00. Last quality={qual:.1f}/10."
