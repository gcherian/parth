"""
Demo — Gap: Teacher-set content sequence (business plan §7.2).

Business plan quote: "The teacher sets the chapter order and the pace in
the console; Parth's between-class sessions follow it. ... our content
spine has to be re-orderable per teacher rather than fixed."

Before this change, modules/curriculum_graph/graph.py's get_next_concept()
picked the next concept purely from the automatic weak-concept/mastery/
exposure heuristic — there was no way for a teacher to declare an order.

This demo runs the real FastAPI `app` in-process (httpx.AsyncClient +
ASGITransport — no bound port, safe alongside other agents hitting the
same shared Postgres) against the actual PUT/GET /teacher/{id}/sequence
endpoints, and calls the real curriculum_graph.graph.get_next_concept()
directly (the same function modules/curriculum_graph/module.py calls on
every /chat turn) to show:

  1. A demo child's automatic next-concept pick (no teacher sequence set).
  2. A demo teacher declaring a sequence that puts a *different* concept
     first via PUT /teacher/{teacher_id}/sequence.
  3. The same child's next-concept pick now follows the teacher's order.
  4. A second, unrelated demo child (no teacher link) is unaffected —
     the automatic path still works exactly as before.

Run: python3 server/tests/demo_gap_teacher_sequence.py
"""
import asyncio
import sys
import uuid
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from main import app  # noqa: E402
from foundation.db import get_pool  # noqa: E402
from foundation.identity import register_pilot_learner, grant_pilot_consent  # noqa: E402
from modules.curriculum_graph import graph  # noqa: E402

DEMO_PREFIX = "demo-sequence-"
TEACHER_ID = f"{DEMO_PREFIX}teacher-1"
GRADE = 7
SUBJECT = "mathematics"

# Deterministic UUIDs derived from demo-prefixed seed strings — foundation.identities
# requires a real UUID primary key, so the human-readable prefix lives in the
# learner's `name` field instead (see setup()).
CHILD_WITH_TEACHER = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{DEMO_PREFIX}child-1"))
CHILD_WITHOUT_TEACHER = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{DEMO_PREFIX}child-2"))

# arithmetic is the shared prerequisite for fractions/decimals/geometry/bodmas/
# data_handling/integers (see foundation/schema.sql seed edges). Mastering it
# makes all of those valid "next concept" candidates.
PREREQ_CONCEPT = "arithmetic"
# geometry is exposed-but-unmastered — the automatic heuristic ranks
# exposures DESC first, so this becomes the deterministic automatic pick.
AUTOMATIC_PICK_CONCEPT = "geometry"
# fractions is a valid candidate too (arithmetic prereq met, unmastered,
# grade-appropriate) but ranks behind geometry automatically (0 exposures,
# lower grade_min) — the teacher will put it first instead.
TEACHER_FIRST_CONCEPT = "fractions"
TEACHER_SEQUENCE = [TEACHER_FIRST_CONCEPT, "decimals", "ratios"]


async def _seed_knowledge(conn, learner_id: str):
    await conn.execute(
        """
        INSERT INTO learner_state.knowledge (learner_id, concept_id, p_mastery, exposures)
        VALUES ($1, $2, 0.90, 3)
        ON CONFLICT (learner_id, concept_id) DO UPDATE
            SET p_mastery = 0.90, exposures = 3
        """,
        learner_id, PREREQ_CONCEPT,
    )
    await conn.execute(
        """
        INSERT INTO learner_state.knowledge (learner_id, concept_id, p_mastery, exposures)
        VALUES ($1, $2, 0.30, 2)
        ON CONFLICT (learner_id, concept_id) DO UPDATE
            SET p_mastery = 0.30, exposures = 2
        """,
        learner_id, AUTOMATIC_PICK_CONCEPT,
    )


async def setup():
    """Create two demo children with identical knowledge state; link only
    the first to a demo teacher via a teacher.portraits row. Idempotent —
    safe to re-run (ON CONFLICT upserts, sequence table cleared explicitly)."""
    for learner_id, seed_name in (
        (CHILD_WITH_TEACHER, f"{DEMO_PREFIX}child-1"),
        (CHILD_WITHOUT_TEACHER, f"{DEMO_PREFIX}child-2"),
    ):
        ok = await register_pilot_learner(learner_id=learner_id, name=seed_name, grade=GRADE)
        assert ok, f"register_pilot_learner failed for {seed_name}"
        await grant_pilot_consent(learner_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _seed_knowledge(conn, CHILD_WITH_TEACHER)
        await _seed_knowledge(conn, CHILD_WITHOUT_TEACHER)

        # Link CHILD_WITH_TEACHER to TEACHER_ID the same way a real teacher
        # would — by submitting a portrait (teacher.portraits.learner_id).
        await conn.execute(
            """
            INSERT INTO teacher.portraits
                (teacher_phone, teacher_name, student_name, student_grade,
                 learner_id, subject, payload, submitted_at)
            VALUES ($1, $2, $3, $4, $5, $6, '{}'::jsonb, now())
            ON CONFLICT (teacher_phone, student_name, subject) DO UPDATE
                SET learner_id = $5, submitted_at = now()
            """,
            TEACHER_ID, f"{DEMO_PREFIX}teacher-1", f"{DEMO_PREFIX}child-1",
            str(GRADE), CHILD_WITH_TEACHER, SUBJECT,
        )

        # Clean slate for this teacher's sequence so re-running the demo is
        # deterministic (this only touches rows for our own demo teacher_id).
        await conn.execute(
            "DELETE FROM curriculum_graph.teacher_sequence WHERE teacher_id = $1",
            TEACHER_ID,
        )


async def main():
    print("=" * 78)
    print("DEMO: Teacher-set content sequence (business plan §7.2)")
    print("=" * 78)

    await setup()

    pool = await get_pool()
    async with pool.acquire() as conn:
        before = await graph.get_next_concept(conn, CHILD_WITH_TEACHER, GRADE, SUBJECT)

    print("\n[1] BEFORE — no teacher sequence set for", TEACHER_ID)
    print(f"    child={CHILD_WITH_TEACHER}")
    print(f"    automatic next concept -> {before}")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://demo-sequence.local") as client:
        put_resp = await client.put(
            f"/teacher/{TEACHER_ID}/sequence",
            json={"concept_ids": TEACHER_SEQUENCE},
        )
        print(f"\n[2] PUT /teacher/{TEACHER_ID}/sequence {TEACHER_SEQUENCE}")
        print(f"    status={put_resp.status_code} body={put_resp.json()}")

        get_resp = await client.get(f"/teacher/{TEACHER_ID}/sequence")
        print(f"\n    GET /teacher/{TEACHER_ID}/sequence -> {get_resp.json()}")

    async with pool.acquire() as conn:
        after = await graph.get_next_concept(conn, CHILD_WITH_TEACHER, GRADE, SUBJECT)
        unaffected = await graph.get_next_concept(conn, CHILD_WITHOUT_TEACHER, GRADE, SUBJECT)

    print("\n[3] AFTER — teacher sequence set, same child, same knowledge state")
    print(f"    next concept -> {after}")

    print("\n[4] Control — second demo child, no teacher link, same knowledge state")
    print(f"    next concept -> {unaffected}")

    # ── Pass/fail ─────────────────────────────────────────────────────────
    checks = {
        "before is the automatic pick (geometry)":
            before is not None and before["concept_id"] == AUTOMATIC_PICK_CONCEPT,
        "after respects the teacher's declared order (fractions)":
            after is not None and after["concept_id"] == TEACHER_FIRST_CONCEPT,
        "before != after (the sequence actually changed the pick)":
            before is not None and after is not None
            and before["concept_id"] != after["concept_id"],
        "PUT /teacher/{id}/sequence returned 200":
            put_resp.status_code == 200,
        "GET /teacher/{id}/sequence reads back what was set":
            get_resp.json().get("sequence") == TEACHER_SEQUENCE,
        "unlinked child's automatic pick is unaffected (geometry)":
            unaffected is not None and unaffected["concept_id"] == AUTOMATIC_PICK_CONCEPT,
    }

    print("\n" + "=" * 78)
    all_ok = True
    for label, ok in checks.items():
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] {label}")
    print("=" * 78)
    print("RESULT:", "PASS" if all_ok else "FAIL")
    print("=" * 78)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
