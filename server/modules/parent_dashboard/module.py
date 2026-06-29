"""
parent.dashboard — All parent-facing data. Nothing parent-facing lives elsewhere.

Subscribes to outbox events. In the critical path, it is only called for
parent.report_requested interactions.
"""
import json
from datetime import datetime

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from foundation.outbox import subscribe

log = get_logger("parent.dashboard")


async def build_report(conn, learner_id: str) -> dict:
    rows = await conn.fetch(
        """
        SELECT subject, emotion, engagement, misconception, created_at
        FROM learner_state.interactions
        WHERE learner_id = $1
        ORDER BY created_at DESC
        LIMIT 50
        """,
        learner_id,
    )
    strong = await conn.fetch(
        """
        SELECT concept_id, p_mastery FROM learner_state.knowledge
        WHERE learner_id = $1 AND p_mastery >= 0.75
        ORDER BY p_mastery DESC LIMIT 5
        """,
        learner_id,
    )
    weak = await conn.fetch(
        """
        SELECT concept_id, p_mastery FROM learner_state.knowledge
        WHERE learner_id = $1 AND p_mastery < 0.5
        ORDER BY p_mastery ASC LIMIT 5
        """,
        learner_id,
    )
    alerts = await conn.fetch(
        """
        SELECT alert_type, message, acknowledged, created_at
        FROM parent_dashboard.alerts
        WHERE learner_id = $1
        ORDER BY created_at DESC LIMIT 10
        """,
        learner_id,
    )

    avg_engagement = sum(r["engagement"] for r in rows) / len(rows) if rows else 5.0
    subjects_covered = list({r["subject"] for r in rows if r["subject"]})
    recent_emotions = [r["emotion"] for r in rows[:5]]
    total_questions = await conn.fetchval(
        "SELECT total_questions FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    ) or 0
    profile_row = await conn.fetchrow(
        "SELECT name, grade, streak_days, last_seen FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    profile_info = dict(profile_row) if profile_row else {}

    report = {
        "learner_id": learner_id,
        "generated_at": datetime.utcnow().isoformat(),
        "learner_name": profile_info.get("name", ""),
        "grade": profile_info.get("grade", 6),
        "streak_days": profile_info.get("streak_days", 0),
        "last_seen": profile_info.get("last_seen", None),
        "total_questions": total_questions,
        "interactions_last_50": len(rows),
        "avg_engagement": round(avg_engagement, 1),
        "subjects_covered": subjects_covered,
        "recent_emotions": recent_emotions,
        "strong_concepts": [dict(r) for r in strong],
        "weak_concepts": [dict(r) for r in weak],
        "recent_alerts": [dict(r) for r in alerts],
    }

    await conn.execute(
        "INSERT INTO parent_dashboard.reports (learner_id, payload) VALUES ($1, $2)",
        learner_id, json.dumps(report, default=str),
    )
    # Record guardian view for the guardian_engaged pilot gate.
    await conn.execute(
        "INSERT INTO parent_dashboard.views (learner_id) VALUES ($1)",
        learner_id,
    )
    return report


class ParentDashboardModule(Module):
    name = "parent.dashboard"
    handles = ["parent.report_requested"]

    def __init__(self):
        # Subscribe to outbox events that drive parent alerts
        subscribe("learner.struggling", self._on_struggling)
        subscribe("learner.milestone_reached", self._on_milestone)

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:  # noqa: E501
        report = await build_report(ctx.db, ctx.learner_id)
        return ModuleResult(data={"report": report})

    async def _on_struggling(self, event_type: str, payload: dict):
        """Create an alert when learner.struggling fires."""
        from foundation.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            learner_id = payload.get("learner_id", "")
            weak = payload.get("weak_concepts", [])
            await conn.execute(
                """
                INSERT INTO parent_dashboard.alerts (learner_id, alert_type, message)
                VALUES ($1, 'struggling', $2)
                """,
                learner_id,
                f"Your child is struggling with: {', '.join(weak)}. "
                "Extra practice is recommended.",
            )
        log.info("parent_alert_created", learner_id=learner_id, type="struggling")

    async def _on_milestone(self, event_type: str, payload: dict):
        """Create a positive alert when a milestone is reached."""
        from foundation.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            learner_id = payload.get("learner_id", "")
            concept = payload.get("concept_id", "")
            await conn.execute(
                """
                INSERT INTO parent_dashboard.alerts (learner_id, alert_type, message)
                VALUES ($1, 'milestone', $2)
                """,
                learner_id,
                f"Your child has mastered: {concept}! Great progress.",
            )
        log.info("parent_alert_created", learner_id=learner_id, type="milestone")

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        conn = ctx.db
        await conn.execute("DELETE FROM parent_dashboard.reports WHERE learner_id = $1", learner_id)
        await conn.execute("DELETE FROM parent_dashboard.alerts WHERE learner_id = $1", learner_id)
        log.info("parent_dashboard_erased", learner_id=learner_id)
