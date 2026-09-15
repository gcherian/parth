"""
Demo for the parent-dashboard authorization gap and its fix.

THE GAP (found reading server/main.py on `main` before this branch):

    @app.get("/parent/{learner_id}/report")
    async def parent_report(learner_id: str, _: None = Depends(rate_limit)):
        _require_uuid(learner_id)
        ...
        report = await build_report(conn, learner_id)
        return report

    @app.get("/parent/{learner_id}/alerts")
    async def parent_alerts(learner_id: str, _: None = Depends(rate_limit)):
        _require_uuid(learner_id)
        ...  # SELECT ... WHERE learner_id = $1

`learner_id` in both routes is the CHILD's id, not the caller's. The only
check is `_require_uuid`, which is a format check (is this a UUID string?),
not an identity or consent check. Anyone who knows — or enumerates — a
valid child UUID gets that child's full mastery/misconception/alert data.
No parent identity, session, or consent link is verified anywhere in
either function.

THE FIX (this branch):

    - foundation/identity.py gains check_parent_access(parent_id, child_id,
      scope), which requires parent_id to be a registered 'guardian'
      identity holding an active (consent_given=true)
      foundation.guardian_links row to that specific child_id, covering
      the requested scope.
    - Both routes move to /parent/{parent_id}/child/{child_id}/report and
      /parent/{parent_id}/child/{child_id}/alerts (matching the URL shape
      of the sibling /transcript endpoint from PR #15) and 403 unless
      check_parent_access() returns True.

This script runs the real `app` object from server/main.py in-process
(httpx.AsyncClient + ASGITransport, no port binding) against the real
shared local Postgres. It seeds one demo child, one real (consented)
parent, and one unrelated registered guardian, all tagged
'demo-parentauthz-' in the `name` column for easy identification/cleanup,
then prints explicit PASS/FAIL lines for:

  1. BEFORE/AFTER: the unrelated caller — who, on the unfixed main route
     shape, would have succeeded with nothing but the child's UUID — is
     now rejected (403) from both /report and /alerts.
  2. The actual verified parent still gets the correct data back from both
     endpoints, unchanged in shape from what build_report()/the alerts
     query have always returned.

Run: python3 server/tests/demo_gap_parent_endpoint_authz.py
(requires the local Postgres from docker-compose to be up and schema
applied — see server/.env DATABASE_URL)
"""
import asyncio
import sys
import uuid
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import httpx  # noqa: E402

from foundation.db import get_pool, apply_schema, close_pool  # noqa: E402
from foundation.identity import register_pilot_learner, grant_pilot_consent  # noqa: E402
from modules.parent_dashboard.module import build_report  # noqa: E402
import main as main_module  # noqa: E402

DEMO_TAG = "demo-parentauthz"
CHILD_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{DEMO_TAG}-child"))
# grant_pilot_consent() derives its synthetic guardian the same way —
# reproduced here so this script knows the real parent's id without
# querying for it.
REAL_PARENT_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pilot-guardian:{CHILD_ID}"))
UNRELATED_PARENT_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{DEMO_TAG}-unrelated-parent"))

_failures = []


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        _failures.append(label)


async def seed():
    await apply_schema()
    ok = await register_pilot_learner(CHILD_ID, f"{DEMO_TAG}-child", grade=6)
    assert ok, "seed: register_pilot_learner failed"
    ok = await grant_pilot_consent(CHILD_ID)
    assert ok, "seed: grant_pilot_consent failed"

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO foundation.identities (id, type, name)
               VALUES ($1, 'guardian', $2)
               ON CONFLICT (id) DO UPDATE SET name = $2""",
            uuid.UUID(UNRELATED_PARENT_ID), f"{DEMO_TAG}-unrelated-parent",
        )
        await conn.execute(
            """INSERT INTO learner_state.knowledge
                   (learner_id, concept_id, p_mastery, exposures, misconceptions)
               VALUES ($1, $2, 0.3, 4, 2)
               ON CONFLICT (learner_id, concept_id) DO UPDATE SET p_mastery = 0.3""",
            CHILD_ID, f"{DEMO_TAG}-fractions",
        )
        await conn.execute(
            """INSERT INTO parent_dashboard.alerts (learner_id, alert_type, message)
               VALUES ($1, 'struggling', $2)""",
            CHILD_ID, f"{DEMO_TAG}: demo alert for gap script",
        )


async def cleanup():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM parent_dashboard.alerts WHERE learner_id = $1", CHILD_ID
        )
        await conn.execute(
            "DELETE FROM parent_dashboard.reports WHERE learner_id = $1", CHILD_ID
        )
        await conn.execute(
            "DELETE FROM parent_dashboard.views WHERE learner_id = $1", CHILD_ID
        )
        await conn.execute(
            "DELETE FROM learner_state.knowledge WHERE learner_id = $1", CHILD_ID
        )
        await conn.execute(
            "DELETE FROM learner_state.profiles WHERE learner_id = $1", CHILD_ID
        )
        await conn.execute(
            "DELETE FROM foundation.guardian_links WHERE child_id = $1",
            uuid.UUID(CHILD_ID),
        )
        await conn.execute(
            "DELETE FROM foundation.identities WHERE id = ANY($1::uuid[])",
            [uuid.UUID(CHILD_ID), uuid.UUID(REAL_PARENT_ID), uuid.UUID(UNRELATED_PARENT_ID)],
        )


async def demonstrate_before():
    print("\n--- BEFORE (main, unfixed): what the old route body did, reproduced directly ---")
    pool = await get_pool()
    async with pool.acquire() as conn:
        # This is exactly what `GET /parent/{learner_id}/report` did on
        # main before this branch: no caller identity, no consent check —
        # just `_require_uuid(learner_id)` (a format check) then
        # `build_report(conn, learner_id)`. Calling it here with only the
        # child's id, standing in for "any caller", to prove it was
        # directly reachable.
        old_report = await build_report(conn, CHILD_ID)
        old_alert_rows = await conn.fetch(
            "SELECT alert_type, message FROM parent_dashboard.alerts WHERE learner_id = $1",
            CHILD_ID,
        )
    check(
        "BEFORE: bare child UUID, no caller identity, returned the child's report",
        old_report.get("learner_id") == CHILD_ID and "weak_concepts" in old_report,
        f"learner_name={old_report.get('learner_name')!r}, "
        f"weak_concepts={len(old_report.get('weak_concepts', []))}",
    )
    check(
        "BEFORE: bare child UUID, no caller identity, returned the child's alerts",
        len(old_alert_rows) >= 1,
        f"{len(old_alert_rows)} alert row(s)",
    )


async def demonstrate_after():
    print("\n--- AFTER (this branch): /parent/{parent_id}/child/{child_id}/... ---")
    transport = httpx.ASGITransport(app=main_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        r = await client.get(f"/parent/{UNRELATED_PARENT_ID}/child/{CHILD_ID}/report")
        check(
            "AFTER: unrelated registered guardian rejected from /report",
            r.status_code == 403,
            f"status={r.status_code}",
        )

        r = await client.get(f"/parent/{UNRELATED_PARENT_ID}/child/{CHILD_ID}/alerts")
        check(
            "AFTER: unrelated registered guardian rejected from /alerts",
            r.status_code == 403,
            f"status={r.status_code}",
        )

        r = await client.get(f"/parent/{REAL_PARENT_ID}/child/{CHILD_ID}/report")
        check(
            "AFTER: verified parent gets 200 from /report",
            r.status_code == 200,
            f"status={r.status_code}",
        )
        if r.status_code == 200:
            body = r.json()
            expected_keys = {
                "learner_id", "generated_at", "learner_name", "grade",
                "strong_concepts", "weak_concepts", "recent_alerts",
                "school_readiness", "learning_ledger",
            }
            check(
                "AFTER: /report shape unchanged (same top-level keys as build_report)",
                expected_keys.issubset(body.keys()) and body["learner_id"] == CHILD_ID,
                f"keys={sorted(body.keys())}",
            )

        r = await client.get(f"/parent/{REAL_PARENT_ID}/child/{CHILD_ID}/alerts")
        check(
            "AFTER: verified parent gets 200 from /alerts",
            r.status_code == 200,
            f"status={r.status_code}",
        )
        if r.status_code == 200:
            body = r.json()
            check(
                "AFTER: /alerts shape unchanged (list of alert_type/message/acknowledged/created_at)",
                isinstance(body, list) and len(body) >= 1
                and {"alert_type", "message", "acknowledged", "created_at"}.issubset(body[0].keys()),
                f"{len(body)} alert row(s)",
            )

        r = await client.get(f"/parent/not-a-uuid/child/{CHILD_ID}/report")
        check(
            "AFTER: malformed parent_id still rejected (400, format check preserved)",
            r.status_code == 400,
            f"status={r.status_code}",
        )


async def main():
    await seed()
    try:
        await demonstrate_before()
        await demonstrate_after()
    finally:
        await cleanup()
        await close_pool()

    print()
    if _failures:
        print(f"RESULT: FAIL ({len(_failures)} check(s) failed: {_failures})")
        sys.exit(1)
    print("RESULT: PASS (all checks passed)")


if __name__ == "__main__":
    asyncio.run(main())
