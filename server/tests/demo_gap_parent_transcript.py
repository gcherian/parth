"""
Standalone demo for gap/parent-transcript-invariant01 (business plan §9,
trust invariant 01: "Never hide a word from the parent").

Runs a short synthetic conversation for a demo child through the real
/chat path (in-process against the real `app`, real Postgres, real
tutor_runtime — no mocking), then calls the new
GET /parent/{parent_id}/child/{child_id}/transcript endpoint as that
child's consented parent and checks the returned transcript matches the
actual conversation verbatim — not a summary, not truncated. Also checks
that an unrelated guardian_id is refused.

Run: python3 server/tests/demo_gap_parent_transcript.py
(from repo root, with the server venv active — or just point the venv's
python3 at this file directly).
"""
import asyncio
import sys
import uuid
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from httpx import AsyncClient, ASGITransport  # noqa: E402

import main as main_mod  # noqa: E402
from foundation.db import get_pool  # noqa: E402
from foundation.identity import register_pilot_learner, grant_pilot_consent  # noqa: E402

DEMO_CHILD_SEED = "demo-transcript-invariant01-child"
CHILD_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, DEMO_CHILD_SEED))

TURNS = [
    ("Why does ice float on water?", "General"),
    ("What is 7 times 8?", "Math"),
    ("Why do leaves turn green?", "Science"),
]


async def _cleanup(conn, child_id: str):
    await conn.execute(
        "DELETE FROM learner_state.interactions WHERE learner_id = $1", child_id
    )
    guardian_rows = await conn.fetch(
        "SELECT guardian_id FROM foundation.guardian_links WHERE child_id = $1",
        uuid.UUID(child_id),
    )
    await conn.execute(
        "DELETE FROM foundation.guardian_links WHERE child_id = $1", uuid.UUID(child_id)
    )
    for r in guardian_rows:
        await conn.execute(
            "DELETE FROM foundation.identities WHERE id = $1", r["guardian_id"]
        )
    await conn.execute(
        "DELETE FROM parent_dashboard.reports WHERE learner_id = $1", child_id
    )
    await conn.execute(
        "DELETE FROM parent_dashboard.alerts WHERE learner_id = $1", child_id
    )
    await conn.execute(
        "DELETE FROM learner_state.profiles WHERE learner_id = $1", child_id
    )
    await conn.execute(
        "DELETE FROM foundation.identities WHERE id = $1", uuid.UUID(child_id)
    )


async def main() -> bool:
    pool = await get_pool()

    async with pool.acquire() as conn:
        print(f"[setup] purging any stale demo rows for {CHILD_ID} ...")
        await _cleanup(conn, CHILD_ID)

    print(f"[setup] registering demo child {CHILD_ID} ({DEMO_CHILD_SEED}) ...")
    ok = await register_pilot_learner(
        learner_id=CHILD_ID, name="demo-transcript-invariant01-child", grade=6
    )
    assert ok, "register_pilot_learner failed"

    print("[setup] granting pilot consent ...")
    ok = await grant_pilot_consent(CHILD_ID)
    assert ok, "grant_pilot_consent failed"

    async with pool.acquire() as conn:
        guardian_row = await conn.fetchrow(
            "SELECT guardian_id FROM foundation.guardian_links WHERE child_id = $1",
            uuid.UUID(CHILD_ID),
        )
        assert guardian_row, "expected a guardian_links row after grant_pilot_consent"
        parent_id = str(guardian_row["guardian_id"])
        await conn.execute(
            "UPDATE foundation.identities SET name = $1 WHERE id = $2",
            "demo-transcript-invariant01-parent",
            guardian_row["guardian_id"],
        )
    print(f"[setup] demo parent (guardian) id = {parent_id}")

    transport = ASGITransport(app=main_mod.app)
    sent_turns = []
    async with AsyncClient(transport=transport, base_url="http://demo") as client:
        print("\n[conversation] sending turns through the real /chat path ...")
        for message, subject in TURNS:
            resp = await client.post(
                "/chat",
                json={
                    "message": message,
                    "subject": subject,
                    "grade": 6,
                    "learner_id": CHILD_ID,
                    "learner_name": "demo-transcript-invariant01-child",
                },
            )
            if resp.status_code != 200:
                print(f"[conversation] /chat failed: {resp.status_code} {resp.text}")
                return False
            body = resp.json()
            sent_turns.append({"question": message, "response": body["response"]})
            print(f"  child: {message}")
            print(f"  parth: {body['response'][:120]}{'...' if len(body['response']) > 120 else ''}")

        print("\n[transcript] fetching as the verified parent ...")
        resp = await client.get(f"/parent/{parent_id}/child/{CHILD_ID}/transcript")
        if resp.status_code != 200:
            print(f"[transcript] endpoint failed: {resp.status_code} {resp.text}")
            return False
        transcript_body = resp.json()

        print("\n[transcript] full transcript returned by the endpoint:")
        for i, turn in enumerate(transcript_body["transcript"], 1):
            print(f"  turn {i} [{turn['created_at']}] subject={turn['subject']}")
            print(f"    Q: {turn['question']}")
            print(f"    A: {turn['response']}")

        print("\n[negative check] an unrelated guardian must be refused ...")
        stranger_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO foundation.identities (id, type, name) VALUES ($1, 'guardian', $2)",
                uuid.UUID(stranger_id), "demo-transcript-invariant01-stranger",
            )
        resp = await client.get(f"/parent/{stranger_id}/child/{CHILD_ID}/transcript")
        stranger_denied = resp.status_code == 403
        print(f"  stranger guardian_id={stranger_id} -> HTTP {resp.status_code} "
              f"({'denied, as expected' if stranger_denied else 'UNEXPECTEDLY ALLOWED'})")
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM foundation.identities WHERE id = $1", uuid.UUID(stranger_id)
            )

    # ── Pass/fail: transcript must match the real conversation verbatim ──────
    returned_turns = [
        {"question": t["question"], "response": t["response"]}
        for t in transcript_body["transcript"]
    ]
    turn_count_ok = transcript_body["turn_count"] == len(TURNS) == len(returned_turns)
    content_ok = returned_turns == sent_turns

    print("\n[result]")
    print(f"  turns sent:      {len(sent_turns)}")
    print(f"  turns returned:  {len(returned_turns)}")
    print(f"  turn count matches: {turn_count_ok}")
    print(f"  content matches verbatim (not summarized/truncated): {content_ok}")
    print(f"  unauthorized guardian correctly denied: {stranger_denied}")

    passed = turn_count_ok and content_ok and stranger_denied
    print(f"\n{'PASS' if passed else 'FAIL'}: parent transcript endpoint "
          f"{'returns the real conversation verbatim and enforces the parent-of-this-child consent gate.' if passed else 'did NOT behave as expected — see above.'}")

    async with pool.acquire() as conn:
        await _cleanup(conn, CHILD_ID)
    print("\n[cleanup] demo rows removed.")

    return passed


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
