"""
Demo — parent weekly report, unified & teacher-attributed (business plan §7.3).

Proves the gap identified in the audit is closed:
  - modules.parent_dashboard.module.build_report() had structured facts
    (mastery, misconceptions, recall-due) but no narrative and no delivery.
  - modules.lens.contextual._generate_narrative() had genuine LLM prose but
    voiced it as a third-party "learning analytics specialist", not the
    teacher, and nothing scheduled or sent it.
  - notify's template registry had no parent-report template at all.

This script seeds one synthetic child (all IDs prefixed demo-parentreport-,
except learner_id itself which must be a UUID — it's deterministically
derived below so re-running this script always targets the same row),
drives the real FastAPI `app` in-process (httpx.AsyncClient + ASGITransport,
no port binding — safe to run alongside other agents against the shared
DB), calls the new POST /teacher/{teacher_phone}/children/{learner_id}/
weekly-report endpoint, and checks the result against three claims:

  (a) attributed to a named teacher, not a third party
  (b) plain English and specific — names the actual misconception
  (c) went through the notify template system (notify.log row + rendered
      template output), not some side-channel string

Run: python3 server/tests/demo_gap_parent_weekly_report.py
"""
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from foundation.db import apply_schema, get_pool  # noqa: E402
from foundation.identity import register_pilot_learner, grant_pilot_consent  # noqa: E402

# ── Demo identities (deterministic — reruns hit the same rows) ────────────────
LEARNER_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "demo-parentreport-learner"))
TEACHER_PHONE = "demo-parentreport-9999999999"
TEACHER_NAME = "Demo Parentreport Teacher Meera"
STUDENT_NAME = "Demo Parentreport Aarav"
PARENT_CONTACT = "demo-parentreport-parent@example.com"

CONCEPT_STRONG = "demo-parentreport-fractions-partwhole"
CONCEPT_WEAK = "demo-parentreport-fractions-denominator"
SUBJECT = "Fractions"  # readable subject name; collision-safe IDs are the UUID/concept/phone above
MISCONCEPTION = "a larger denominator means a larger number"


async def seed(pool) -> None:
    await register_pilot_learner(LEARNER_ID, name=STUDENT_NAME, grade=6, school_id="demo-parentreport-school")
    ok = await grant_pilot_consent(LEARNER_ID)
    assert ok, "consent grant failed — cannot proceed"

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO learner_state.knowledge
                   (learner_id, concept_id, exposures, demonstrations, misconceptions, p_mastery)
               VALUES ($1, $2, 8, 6, 0, 0.82)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET p_mastery = 0.82, exposures = 8, demonstrations = 6, misconceptions = 0""",
            LEARNER_ID, CONCEPT_STRONG,
        )
        await conn.execute(
            """INSERT INTO learner_state.knowledge
                   (learner_id, concept_id, exposures, demonstrations, misconceptions, p_mastery)
               VALUES ($1, $2, 5, 1, 3, 0.35)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET p_mastery = 0.35, exposures = 5, demonstrations = 1, misconceptions = 3""",
            LEARNER_ID, CONCEPT_WEAK,
        )
        await conn.execute(
            """INSERT INTO learner_state.interactions
                   (learner_id, subject, misconception, emotion, engagement, created_at)
               VALUES ($1, $2, $3, 'curious', 7.0, now())""",
            LEARNER_ID, SUBJECT, MISCONCEPTION,
        )
        await conn.execute(
            """INSERT INTO practice_engine.cards
                   (learner_id, concept_id, next_review, repetitions)
               VALUES ($1, $2, now() - interval '1 day', 2)
               ON CONFLICT (learner_id, concept_id) DO UPDATE
                   SET next_review = now() - interval '1 day', repetitions = 2""",
            LEARNER_ID, CONCEPT_STRONG,
        )
        await conn.execute(
            "UPDATE learner_state.profiles SET streak_days = 4 WHERE learner_id = $1",
            LEARNER_ID,
        )


async def main() -> int:
    await apply_schema()
    pool = await get_pool()
    await seed(pool)

    from main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo.local") as client:
        resp = await client.post(
            f"/teacher/{TEACHER_PHONE}/children/{LEARNER_ID}/weekly-report",
            json={
                "teacher_name": TEACHER_NAME,
                "parent_contact": PARENT_CONTACT,
                "channel": "email",
            },
        )

    print("=" * 78)
    print(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        print("FAIL: endpoint did not return 200")
        return 1

    result = resp.json()
    narrative = result["narrative"]

    print(f"\nWeek: {result['week_start']}")
    print(f"Teacher: {result['teacher_name']}")
    print(f"Student: {result['student_name']}")
    print("\n--- Parent weekly report (as generated) ---")
    print(narrative)
    print("--- notify dispatch result ---")
    print(result["notify"])
    print("=" * 78)

    checks = []

    # (a) attributed to a named teacher, not a third party
    attributed = TEACHER_NAME in narrative or TEACHER_NAME.split()[-1] in narrative
    not_third_party = "learning analytics specialist" not in narrative.lower()
    checks.append(("(a) attributed to named teacher, not a third party",
                    attributed and not_third_party))

    # (b) plain English and specific — names the actual misconception, not a bare score
    names_misconception = MISCONCEPTION in narrative
    checks.append(("(b) specific — names the actual misconception verbatim",
                    names_misconception))

    # (c) went through the notify template system
    pool = await get_pool()
    async with pool.acquire() as conn:
        log_row = await conn.fetchrow(
            """SELECT recipient, channel, template, status FROM notify.log
               WHERE recipient = $1 AND template = 'parent_weekly_report'
               ORDER BY sent_at DESC LIMIT 1""",
            PARENT_CONTACT,
        )
        report_row = await conn.fetchrow(
            """SELECT teacher_name, narrative, notified FROM parent_dashboard.weekly_reports
               WHERE learner_id = $1 AND teacher_phone = $2""",
            LEARNER_ID, TEACHER_PHONE,
        )
    went_through_notify = (
        log_row is not None
        and log_row["template"] == "parent_weekly_report"
        and report_row is not None
        and report_row["narrative"] == narrative
    )
    checks.append(("(c) went through notify's template system (notify.log + weekly_reports row)",
                    went_through_notify))

    print("\n--- Checks ---")
    all_pass = True
    for label, ok in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {label}")
        all_pass = all_pass and ok

    if log_row is not None:
        print(f"\nnotify.log: recipient={log_row['recipient']} channel={log_row['channel']} "
              f"template={log_row['template']} status={log_row['status']}")
    if report_row is not None:
        print(f"parent_dashboard.weekly_reports: teacher_name={report_row['teacher_name']} "
              f"notified={report_row['notified']}")

    print("\n" + ("ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
