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
    concept_rows = await conn.fetch(
        """
        SELECT concept_id, p_mastery, exposures, misconceptions, last_updated
        FROM learner_state.knowledge
        WHERE learner_id = $1
        ORDER BY last_updated DESC
        LIMIT 20
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
    recall_due = await conn.fetch(
        """
        SELECT concept_id, next_review, repetitions
        FROM practice_engine.cards
        WHERE learner_id = $1 AND next_review <= now()
        ORDER BY next_review ASC
        LIMIT 5
        """,
        learner_id,
    )
    recent_misconceptions = await conn.fetch(
        """
        SELECT misconception, subject, created_at
        FROM learner_state.interactions
        WHERE learner_id = $1
          AND misconception IS NOT NULL
          AND misconception <> ''
        ORDER BY created_at DESC
        LIMIT 5
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
        """
        SELECT name, grade, streak_days, last_seen, analogy_scores
        FROM learner_state.profiles
        WHERE learner_id = $1
        """,
        learner_id,
    )
    profile_info = dict(profile_row) if profile_row else {}
    concepts = [dict(r) for r in concept_rows]
    concept_count = len(concepts)
    avg_mastery = (
        sum(float(c["p_mastery"] or 0.0) for c in concepts) / concept_count
        if concept_count else 0.0
    )
    readiness_score = round(avg_mastery * 100)
    if concept_count == 0:
        readiness_label = "Needs diagnostic"
    elif readiness_score >= 75:
        readiness_label = "Test-ready"
    elif readiness_score >= 55:
        readiness_label = "Close, with risks"
    else:
        readiness_label = "Needs guided practice"

    top_risks = [
        {
            "concept_id": c["concept_id"],
            "p_mastery": c["p_mastery"],
            "misconceptions": c["misconceptions"],
        }
        for c in sorted(
            concepts,
            key=lambda c: (float(c["p_mastery"] or 0.0), -int(c["misconceptions"] or 0)),
        )[:3]
        if float(c["p_mastery"] or 0.0) < 0.65
    ]
    analogy_scores = profile_info.get("analogy_scores") or {}
    if isinstance(analogy_scores, str):
        try:
            analogy_scores = json.loads(analogy_scores)
        except json.JSONDecodeError:
            analogy_scores = {}
    preferred_anchors = [
        {"anchor": k, "score": v}
        for k, v in sorted(
            analogy_scores.items(),
            key=lambda item: float(item[1] or 0.0),
            reverse=True,
        )[:3]
    ]

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
        "school_readiness": {
            "score": readiness_score,
            "label": readiness_label,
            "concepts_seen": concept_count,
            "ready_topics_count": len(strong),
            "risk_topics_count": len(top_risks),
            "recall_due_count": len(recall_due),
            "top_risks": top_risks,
            "recall_due": [dict(r) for r in recall_due],
            "test_focus": (
                "Start with a short diagnostic."
                if concept_count == 0
                else "Revise the risk topics first, then test recall without hints."
            ),
        },
        "learning_ledger": {
            "concepts_tracked": concept_count,
            "misconceptions_seen": len(recent_misconceptions),
            "recent_misconceptions": [dict(r) for r in recent_misconceptions],
            "preferred_anchors": preferred_anchors,
            "explanation": (
                "Marks are the output signal. Parth tracks the causes underneath: "
                "mastery, recall, misconceptions, and examples that actually land."
            ),
        },
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
