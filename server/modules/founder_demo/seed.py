"""
Seeds one coherent, named narrative for the founder/investor demo:
Aarav Sharma (Class 6, Pune) — the exact persona worked through in the
business plan itself (§2.1, §5.2) — his teacher Priya Iyer, and his mother
Sunita Sharma, plus five classmates so Priya's Tuesday briefing has a real
shared misconception to show.

Deliberately reuses the exact seeding shape already verified in
server/tests/demo_gap_teacher_briefing.py and demo_gap_parent_weekly_report.py
(same concept ids, same mastery thresholds, same table writes) — just with
investor-presentable names instead of demo-briefing-1/2/3, so the already-
proven-reliable behavior (shared-misconception grouping, ready-to-advance
detection, quiet-child detection) carries over unchanged.

Idempotent — safe to call again (e.g. if the presenter reloads the page
mid-demo); every write is an upsert or a plain insert-if-absent.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

from foundation.db import get_pool
from foundation.identity import register_pilot_learner, grant_pilot_consent
from kernel.agent import AgentSignals
from modules.learner_state.agents.rhythm_time_steward import RhythmTimeStewardAgent

AARAV_ID = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "founder-demo-aarav-sharma"))
AARAV_NAME = "Aarav Sharma"

TEACHER_PHONE = "9876543210"
TEACHER_NAME = "Priya Iyer"

PARENT_ID = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"pilot-guardian:{AARAV_ID}"))
PARENT_NAME = "Sunita Sharma"

CONCEPT_WEAK = "fractions"
CONCEPT_STRONG = "decimals"
MISCONCEPTION = (
    "Believes a larger denominator always means a larger fraction — hasn't "
    "yet connected denominator size to how small each part becomes."
)

# suffix: (display name, fractions p_mastery, shares the misconception?, days quiet)
CLASSMATES = {
    "ishaan-verma": ("Ishaan Verma", 0.40, True, 0),
    "diya-kapoor":  ("Diya Kapoor", 0.50, True, 0),
    "kabir-nair":   ("Kabir Nair", 0.90, False, 0),
    "ananya-rao":   ("Ananya Rao", 0.92, False, 0),
    "meera-joshi":  ("Meera Joshi", 0.80, False, 9),
}


def _slug_id(suffix: str) -> str:
    return f"founder-demo-{suffix}"


async def seed() -> dict:
    ok = await register_pilot_learner(AARAV_ID, name=AARAV_NAME, grade=6, school_id="founder-demo-school")
    if not ok:
        raise RuntimeError("register_pilot_learner failed for Aarav")
    await grant_pilot_consent(AARAV_ID)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE foundation.identities SET name = $1 WHERE id = $2",
            PARENT_NAME, _uuid.UUID(PARENT_ID),
        )

        # ── Aarav: weak on fractions (the shared misconception), strong on decimals ──
        # A live /chat turn during rehearsal can make the real tutor pipeline
        # write its own knowledge/practice rows on unrelated concepts (e.g.
        # "arithmetic", from analysing a cricket run-rate question) — wipe
        # anything outside the two concepts this demo actually seeds, so
        # gather_report_facts's weak/strong/recall-due picks stay deterministic
        # across repeated rehearsals.
        await conn.execute(
            "DELETE FROM learner_state.knowledge WHERE learner_id = $1 AND concept_id NOT IN ($2, $3)",
            AARAV_ID, CONCEPT_WEAK, CONCEPT_STRONG,
        )
        await conn.execute(
            "DELETE FROM practice_engine.cards WHERE learner_id = $1 AND concept_id NOT IN ($2, $3)",
            AARAV_ID, CONCEPT_WEAK, CONCEPT_STRONG,
        )
        await conn.execute(
            """INSERT INTO learner_state.knowledge
                   (learner_id, concept_id, exposures, demonstrations, p_mastery)
               VALUES ($1, $2, 8, 4, 0.45)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET p_mastery = 0.45, exposures = 8, demonstrations = 4""",
            AARAV_ID, CONCEPT_WEAK,
        )
        await conn.execute(
            """INSERT INTO learner_state.knowledge
                   (learner_id, concept_id, exposures, demonstrations, p_mastery)
               VALUES ($1, $2, 8, 6, 0.82)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET p_mastery = 0.82, exposures = 8, demonstrations = 6""",
            AARAV_ID, CONCEPT_STRONG,
        )
        # Wipe ALL of Aarav's misconceptions, not just the seeded one — a live
        # /chat turn during rehearsal can add the tutor's own (real, separate)
        # misconception tag on a different concept with a newer last_seen,
        # which would otherwise outrank the seeded one in the Tuesday
        # briefing's "most recent misconception per learner" query and knock
        # Aarav out of his own shared-misconception group. Reset must be a
        # true reset regardless of how much the presenter has already clicked.
        await conn.execute(
            "DELETE FROM learner_state.misconception_map WHERE learner_id = $1",
            AARAV_ID,
        )
        await conn.execute(
            """INSERT INTO learner_state.misconception_map (learner_id, concept_id, misconception)
               VALUES ($1, $2, $3)""",
            AARAV_ID, CONCEPT_WEAK, MISCONCEPTION,
        )
        # Clear every real chat turn from prior rehearsals too — otherwise
        # the Student tab's transcript accumulates one entry per past
        # rehearsal run forever, instead of showing one clean conversation.
        await conn.execute(
            "DELETE FROM learner_state.interactions WHERE learner_id = $1",
            AARAV_ID,
        )
        await conn.execute(
            """INSERT INTO learner_state.interactions
                   (learner_id, subject, misconception, emotion, engagement, created_at)
               VALUES ($1, 'Mathematics', $2, 'curious', 7.0, now())""",
            AARAV_ID, MISCONCEPTION,
        )
        await conn.execute(
            """INSERT INTO practice_engine.cards (learner_id, concept_id, next_review, repetitions)
               VALUES ($1, $2, now() - interval '1 day', 2)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET next_review = now() - interval '1 day', repetitions = 2""",
            AARAV_ID, CONCEPT_STRONG,
        )
        await conn.execute(
            "UPDATE learner_state.profiles SET streak_days = 6 WHERE learner_id = $1",
            AARAV_ID,
        )
        existing_alert = await conn.fetchval(
            "SELECT 1 FROM parent_dashboard.alerts WHERE learner_id = $1 AND alert_type = 'milestone'",
            AARAV_ID,
        )
        if not existing_alert:
            await conn.execute(
                """INSERT INTO parent_dashboard.alerts (learner_id, alert_type, message)
                   VALUES ($1, 'milestone', $2)""",
                AARAV_ID, "Your child has mastered: decimals! Great progress.",
            )

        # ── Aarav's real-focus-time signal, for the chrono-ritual screen ──────
        # Clear any appointment confirmed in a prior rehearsal — the
        # narrative script's step 6 demonstrates the confirm ACTION, which
        # needs to start from "suggested, unconfirmed" every time.
        await conn.execute(
            "DELETE FROM learner_state.session_appointment WHERE learner_id = $1",
            AARAV_ID,
        )
        agent = RhythmTimeStewardAgent()
        signals = AgentSignals(learner_id=AARAV_ID, session_id="founder-demo-session", phase="post", engagement=8.0)
        await agent.observe(signals, conn)

        # ── Classmates: just enough for Priya's Tuesday briefing to have a
        # real batch (learner_state tables key on free-text learner_id — no
        # foundation.identities row needed for a non-chatting classmate) ────
        now = datetime.now(timezone.utc)
        for suffix, (name, mastery, shares_misconception, quiet_days) in CLASSMATES.items():
            learner_id = _slug_id(suffix)
            last_seen = now - timedelta(days=quiet_days)
            await conn.execute(
                """INSERT INTO learner_state.profiles (learner_id, name, grade, last_seen)
                   VALUES ($1, $2, 6, $3)
                   ON CONFLICT (learner_id) DO UPDATE SET last_seen = $3, name = $2""",
                learner_id, name, last_seen,
            )
            await conn.execute(
                """INSERT INTO learner_state.knowledge
                       (learner_id, concept_id, exposures, demonstrations, p_mastery, last_updated)
                   VALUES ($1, $2, 8, 5, $3, now())
                   ON CONFLICT (learner_id, concept_id) DO UPDATE
                       SET p_mastery = $3, last_updated = now()""",
                learner_id, CONCEPT_WEAK, mastery,
            )
            if shares_misconception:
                await conn.execute(
                    """DELETE FROM learner_state.misconception_map
                       WHERE learner_id = $1 AND concept_id = $2""",
                    learner_id, CONCEPT_WEAK,
                )
                await conn.execute(
                    """INSERT INTO learner_state.misconception_map (learner_id, concept_id, misconception)
                       VALUES ($1, $2, $3)""",
                    learner_id, CONCEPT_WEAK, MISCONCEPTION,
                )
            await conn.execute(
                """INSERT INTO teacher.portraits
                       (teacher_phone, teacher_name, student_name, student_grade, subject,
                        learner_id, payload, submitted_at)
                   VALUES ($1, $2, $3, '6', 'mathematics', $4, '{}'::jsonb, now())
                   ON CONFLICT (teacher_phone, student_name, subject) DO UPDATE
                       SET learner_id = $4, submitted_at = now()""",
                TEACHER_PHONE, TEACHER_NAME, name, learner_id,
            )

        # ── Aarav himself, linked into the same batch ─────────────────────
        await conn.execute(
            """INSERT INTO teacher.portraits
                   (teacher_phone, teacher_name, student_name, student_grade, subject,
                    learner_id, payload, submitted_at)
               VALUES ($1, $2, $3, '6', 'mathematics', $4, '{}'::jsonb, now())
               ON CONFLICT (teacher_phone, student_name, subject) DO UPDATE
                   SET learner_id = $4, submitted_at = now()""",
            TEACHER_PHONE, TEACHER_NAME, AARAV_NAME, AARAV_ID,
        )

    return {
        "child_id": AARAV_ID,
        "child_name": AARAV_NAME,
        "teacher_phone": TEACHER_PHONE,
        "teacher_name": TEACHER_NAME,
        "parent_id": PARENT_ID,
        "parent_name": PARENT_NAME,
        "weak_concept": CONCEPT_WEAK,
        "strong_concept": CONCEPT_STRONG,
        "misconception": MISCONCEPTION,
    }
