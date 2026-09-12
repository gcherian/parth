"""
Demo — Invariant 03 server-side contract (business plan §9).

    "Never use the camera for monitoring. Commitment: Focus and fatigue
    inferred on-device from conversation only. Enforcement: Federated
    attention layer — raw signals never leave the phone; only coarse state
    is transmitted."

The on-device inference is a mobile-client capability and is NOT built
here. This demo proves the *server-side* half of the guarantee, i.e. that
POST /attention/coarse-state (modules/attention_coarse/routes.py):

  1. Accepts a valid coarse-state payload for a consented demo child and
     stores only the coarse enum state.
  2. Rejects a payload carrying a raw-signal-shaped field (a fake base64
     image blob), with an explicit error — before anything is stored.

Runs against the real `app` object in-process (httpx.AsyncClient +
ASGITransport — no port binding, safe next to other agents hitting the
same shared DB) and against the real shared Postgres instance.

Usage:
    python3 server/tests/demo_gap_attention_invariant03.py
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import httpx

from foundation.db import get_pool
from foundation.identity import register_pilot_learner, grant_pilot_consent

# Deterministic per this demo — reruns reuse the same identity row instead of
# growing a new one, and the name is prefixed so it's greppable/collision-safe
# alongside the other agents' demo-* rows in the shared foundation.identities
# table. (child_id itself must be a real UUID — see foundation/identity.py
# and main.py's _require_uuid — so the human-readable "demo-attention-"
# label lives in the `name` column, not the id.)
_DEMO_NAME = "demo-attention-invariant03-child"
_DEMO_CHILD_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, _DEMO_NAME))
_DEMO_SESSION_ID = "demo-attention-session-1"


async def _setup_demo_learner() -> None:
    ok = await register_pilot_learner(_DEMO_CHILD_ID, _DEMO_NAME, grade=6)
    assert ok, "failed to register demo learner"
    ok = await grant_pilot_consent(_DEMO_CHILD_ID)
    assert ok, "failed to grant demo consent"


async def _row_count(child_id: str, session_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM attention_coarse.states "
            "WHERE child_id = $1 AND session_id = $2",
            uuid.UUID(child_id), session_id,
        )


async def _row_exists(child_id: str, session_id: str, ts: str, state: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM attention_coarse.states "
            "WHERE child_id = $1 AND session_id = $2 AND ts = $3 AND state = $4",
            uuid.UUID(child_id), session_id, ts, state,
        )
        return row is not None


async def main() -> bool:
    from main import app  # import after sys.path setup, real app object

    passed = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://demo.local"
    ) as client:
        await _setup_demo_learner()

        # Fresh ts per run so reruns exercise a brand-new row rather than
        # colliding with a previous run's (child_id, session_id, ts) — the
        # dedup unique index is tested separately below, deliberately.
        run_ts = datetime.now(timezone.utc).replace(microsecond=0)
        run_ts_iso = run_ts.isoformat().replace("+00:00", "Z")

        # ── Case 1: valid coarse-state payload is accepted and stored ──────
        valid_payload = {
            "child_id": _DEMO_CHILD_ID,
            "session_id": _DEMO_SESSION_ID,
            "state": "focused",
            "ts": run_ts_iso,
        }
        r1 = await client.post("/attention/coarse-state", json=valid_payload)
        stored = await _row_exists(_DEMO_CHILD_ID, _DEMO_SESSION_ID, run_ts, "focused")

        case1_ok = r1.status_code == 200 and stored
        print(f"[{'PASS' if case1_ok else 'FAIL'}] Case 1 — valid coarse state accepted & stored: "
              f"status={r1.status_code}, row_stored={stored}, body={r1.json()}")
        passed &= case1_ok

        # ── Case 1b: re-posting the identical payload is idempotent ────────
        before_dupe = await _row_count(_DEMO_CHILD_ID, _DEMO_SESSION_ID)
        r1b = await client.post("/attention/coarse-state", json=valid_payload)
        after_dupe = await _row_count(_DEMO_CHILD_ID, _DEMO_SESSION_ID)
        case1b_ok = r1b.status_code == 200 and after_dupe == before_dupe
        print(f"[{'PASS' if case1b_ok else 'FAIL'}] Case 1b — duplicate post is idempotent (no extra row): "
              f"status={r1b.status_code}, rows_before={before_dupe}, rows_after={after_dupe}")
        passed &= case1b_ok

        # ── Case 2: payload with a simulated raw-signal field is rejected ──
        raw_signal_payload = {
            "child_id": _DEMO_CHILD_ID,
            "session_id": _DEMO_SESSION_ID,
            "state": "focused",
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        }
        before2 = await _row_count(_DEMO_CHILD_ID, _DEMO_SESSION_ID)
        r2 = await client.post("/attention/coarse-state", json=raw_signal_payload)
        after2 = await _row_count(_DEMO_CHILD_ID, _DEMO_SESSION_ID)

        case2_ok = r2.status_code == 422 and after2 == before2
        detail = r2.json().get("detail", {})
        print(f"[{'PASS' if case2_ok else 'FAIL'}] Case 2 — raw-signal payload rejected: "
              f"status={r2.status_code}, rows_before={before2}, rows_after={after2}, "
              f"error={detail if isinstance(detail, dict) else detail}")
        passed &= case2_ok

    return bool(passed)


if __name__ == "__main__":
    ok = asyncio.run(main())
    print()
    print("RESULT:", "ALL PASS" if ok else "FAILURE")
    sys.exit(0 if ok else 1)
