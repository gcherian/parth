"""
Standalone demo for the teacher "Tuesday briefing" endpoint
(GET /teacher/{teacher_id}/briefing — modules/teacher/briefing.py).

Run: python3 server/tests/demo_gap_teacher_briefing.py

Seeds six synthetic children (IDs prefixed demo-briefing-) under one demo
teacher with realistic learner_state:
  - Aisha, Rohan, Meera  — share the same fractions misconception
  - Priya, Dev           — already ahead of the batch on fractions
  - Sana                 — previously cleared fractions, gone quiet

Then calls the real FastAPI `app` object in-process (httpx.AsyncClient +
ASGITransport — no port bound, so it can't collide with other agents
running against this same shared DB) and prints the briefing, followed by
explicit PASS/FAIL lines checking it reads the way business plan §7.1
requires: named, specific, short, no raw scores, no instructions to the
teacher.

Cleans up its own demo-briefing-* rows before and after running, so it's
safe to re-run.
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import httpx  # noqa: E402

TEACHER_ID = "demo-briefing-teacher-1"

CHILDREN = {
    # learner_id suffix: (display name, fractions p_mastery, misconception text or None, days_since_last_seen)
    "aisha": ("Aisha", 0.45, "shared", 0),
    "rohan": ("Rohan", 0.50, "shared", 0),
    "meera": ("Meera", 0.40, "shared", 0),
    "priya": ("Priya", 0.90, None, 0),
    "dev":   ("Dev",   0.92, None, 0),
    "sana":  ("Sana",  0.80, None, 9),
}

SHARED_MISCONCEPTION = (
    "Believes fraction addition keeps the same denominator and just adds "
    "the numerators, without finding a common denominator."
)


def _learner_id(suffix: str) -> str:
    return f"demo-briefing-{suffix}"


async def _cleanup(conn):
    learner_ids = [_learner_id(s) for s in CHILDREN]
    await conn.execute("DELETE FROM teacher.portraits WHERE teacher_phone = $1", TEACHER_ID)
    await conn.execute("DELETE FROM learner_state.misconception_map WHERE learner_id = ANY($1::text[])", learner_ids)
    await conn.execute("DELETE FROM learner_state.knowledge WHERE learner_id = ANY($1::text[])", learner_ids)
    await conn.execute("DELETE FROM learner_state.profiles WHERE learner_id = ANY($1::text[])", learner_ids)


async def _seed(conn):
    """Not a learner-data-mutation helper subject to CONVENTIONS.md's
    checklist (no real child behind it) — synthetic demo fixtures only,
    deleted by _cleanup() below."""
    now = datetime.now(timezone.utc)
    for suffix, (name, mastery, misconception, quiet_days) in CHILDREN.items():
        learner_id = _learner_id(suffix)
        last_seen = now - timedelta(days=quiet_days)

        await conn.execute(
            """
            INSERT INTO learner_state.profiles (learner_id, name, grade, last_seen)
            VALUES ($1, $2, 7, $3)
            ON CONFLICT (learner_id) DO UPDATE SET last_seen = $3, name = $2
            """,
            learner_id, name, last_seen,
        )
        await conn.execute(
            """
            INSERT INTO learner_state.knowledge
                (learner_id, concept_id, exposures, demonstrations, p_mastery, last_updated)
            VALUES ($1, 'fractions', 8, 6, $2, now())
            ON CONFLICT (learner_id, concept_id) DO UPDATE SET p_mastery = $2, last_updated = now()
            """,
            learner_id, mastery,
        )
        if misconception:
            await conn.execute(
                """
                INSERT INTO learner_state.misconception_map (learner_id, concept_id, misconception)
                VALUES ($1, 'fractions', $2)
                """,
                learner_id, SHARED_MISCONCEPTION,
            )
        await conn.execute(
            """
            INSERT INTO teacher.portraits
                (teacher_phone, teacher_name, student_name, subject, learner_id, payload, submitted_at)
            VALUES ($1, 'Demo Teacher', $2, 'maths', $3, '{}'::jsonb, now())
            ON CONFLICT (teacher_phone, student_name, subject) DO UPDATE
                SET learner_id = $3, submitted_at = now()
            """,
            TEACHER_ID, name, learner_id,
        )


def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    return condition


async def main() -> int:
    import foundation.db as db_mod

    db_mod._pool = None
    await db_mod.apply_schema()
    pool = await db_mod.get_pool()

    async with pool.acquire() as conn:
        await _cleanup(conn)
        await _seed(conn)

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo.local") as client:
        resp = await client.get(f"/teacher/{TEACHER_ID}/briefing")

    async with pool.acquire() as conn:
        await _cleanup(conn)

    print("\n=== GET /teacher/{teacher_id}/briefing — raw response ===")
    print(f"status: {resp.status_code}")
    body = resp.json()
    print(json.dumps(body, indent=2, default=str))

    print("\n=== Rendered as a teacher would read it ===")
    sm = body.get("shared_misconception")
    lines = []
    if sm:
        lines.append(
            f"{sm['count']} of your {body['batch_size']} are carrying the same "
            f"misconception on {sm['concept']}: {sm['belief']}"
        )
        lines.append(f"Named: {', '.join(sm['children'])}")
        lines.append(f"Opener: {sm['opener']}")
    for q in body.get("quiet_children", []):
        lines.append(f"{q['name']} has gone quiet ({q['quiet_for_days']} days) on {q['concept']}, which they'd cleared.")
    for r in body.get("ready_to_advance", []):
        lines.append(f"{r['name']} is ready to move past {r['concept']} — {r['next']}.")
    rendered = "\n".join(lines)
    print(rendered)

    print("\n=== Pass/fail checks ===")
    results = []

    results.append(_check("HTTP 200", resp.status_code == 200, f"got {resp.status_code}"))
    results.append(_check("batch_size == 6", body.get("batch_size") == 6, f"got {body.get('batch_size')}"))

    results.append(_check(
        "shared misconception found, named, count == 3",
        bool(sm) and sm.get("count") == 3,
        json.dumps(sm) if sm else "none",
    ))
    if sm:
        results.append(_check(
            "shared misconception names the right three children",
            set(sm["children"]) == {"Aisha", "Rohan", "Meera"},
            str(sm["children"]),
        ))
        results.append(_check(
            "belief is a plain-language sentence, not a raw label",
            len(sm["belief"]) > 20 and "denominator" in sm["belief"].lower(),
        ))
        results.append(_check(
            "opener is non-empty and reasonably short (a few sentences, not an essay)",
            0 < len(sm["opener"]) < 600,
            f"{len(sm['opener'])} chars",
        ))

    quiet = body.get("quiet_children", [])
    results.append(_check(
        "exactly one quiet child, named Sana, on a cleared concept",
        len(quiet) == 1 and quiet[0]["name"] == "Sana" and quiet[0]["quiet_for_days"] >= 6,
        json.dumps(quiet),
    ))

    ready = body.get("ready_to_advance", [])
    results.append(_check(
        "exactly two children ready to advance, named Priya and Dev",
        len(ready) == 2 and {r["name"] for r in ready} == {"Priya", "Dev"},
        json.dumps(ready),
    ))

    raw_json = json.dumps(body)
    results.append(_check(
        "no raw scores leak into the response (no p_mastery / engagement_score fields)",
        "p_mastery" not in raw_json and "engagement_score" not in raw_json,
    ))

    # Scan everything the teacher reads EXCEPT the opener: the opener is
    # explanatory content for the child ("first find a common denominator"
    # is instructive math, not an instruction to the teacher), while every
    # other field is the briefing's own narration and must stay descriptive.
    scan_obj = json.loads(raw_json)
    if scan_obj.get("shared_misconception"):
        scan_obj["shared_misconception"] = {
            k: v for k, v in scan_obj["shared_misconception"].items() if k != "opener"
        }
    directive_phrases = ["you should", "please ", "you must", "recommend", "need to ", "instruct", "tell him", "tell her"]
    scan_text = json.dumps(scan_obj).lower()
    found_directive = [p for p in directive_phrases if p in scan_text]
    results.append(_check(
        "never phrased as an instruction to the teacher (no directive language outside the opener)",
        not found_directive,
        str(found_directive) if found_directive else "",
    ))

    reading_text = rendered
    results.append(_check(
        "reads short enough for a 90-second phone read (~under 900 characters of body text)",
        len(reading_text) < 900,
        f"{len(reading_text)} chars",
    ))

    all_passed = all(results)
    print(f"\n{'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
