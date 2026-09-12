"""
Standalone demo — Chrono-learning ritual confirmation (business plan §8.4).

Gap this closes: rhythm_time_steward infers a peak-focus window per child,
but there was no parent-facing flow to confirm or adjust that inference into
a fixed, scheduled "appointment" (business plan §8.4). This demo:

  1. Runs the REAL rhythm_time_steward agent to produce a genuine inferred
     peak-focus hour for a demo child (no mocking of the inference itself).
  2. Hits the new /chrono-ritual/{learner_id}/window endpoint (via the real
     FastAPI `app`, in-process, no port binding) to show that inferred
     window to a "parent".
  3. Has a demo parent confirm/adjust it via POST /chrono-ritual/{id}/confirm.
  4. Shows the confirmed appointment is now stored and retrievable.
  5. Shows two real downstream readers — rhythm_time_steward's own live
     context read, and the contextual lens's session pattern — now prefer
     the confirmed appointment over the raw inference.
  6. Scans every piece of text this feature produced for streak/guilt/
     punitive language (Invariant 04, business plan §9) and prints an
     explicit PASS/FAIL.

Run: python3 server/tests/demo_gap_chrono_ritual.py
(from repo root), or python3 tests/demo_gap_chrono_ritual.py from server/.
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import httpx  # noqa: E402

from foundation.db import get_pool, close_pool  # noqa: E402
from kernel.agent import AgentSignals  # noqa: E402
from modules.learner_state.agents.rhythm_time_steward import RhythmTimeStewardAgent  # noqa: E402

# Banned language (Invariant 04, business plan §9): "It is an appointment,
# not a streak." — none of these substrings may appear in anything this
# feature says to a parent or a child.
_BANNED_SUBSTRINGS = [
    "streak", "miss", "missed", "in a row", "consecutive",
    "shame", "guilt", "punish", "penalt", "fail to", "urgent", "warning:",
]


def _scan(label: str, text: str, findings: list[str]) -> None:
    lowered = text.lower()
    for bad in _BANNED_SUBSTRINGS:
        if bad in lowered:
            findings.append(f"{label!r} contains banned substring {bad!r}")


async def main() -> int:
    learner_id = f"demo-chrono-{uuid.uuid4().hex[:10]}"
    parent_id = "demo-chrono-parent-anita"
    checked_texts: list[tuple[str, str]] = []

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Idempotent rerun-safety: clear any prior demo rows for this exact id.
        await conn.execute("DELETE FROM learner_state.session_appointment WHERE learner_id = $1", learner_id)
        await conn.execute("DELETE FROM learner_state.rhythm_state WHERE learner_id = $1", learner_id)

        # ── Step 1: produce a REAL inference via rhythm_time_steward ────────
        agent = RhythmTimeStewardAgent()
        signals = AgentSignals(
            learner_id=learner_id, session_id="demo-session-1", phase="post",
            engagement=8.0,
        )
        await agent.observe(signals, conn)  # real _observe, writes rhythm_state
        read_before = await agent.read(conn, learner_id)  # real _read
        checked_texts.append(("rhythm_time_steward.read (before confirmation)", read_before))
        print(f"Demo child: {learner_id}")
        print(f"1) rhythm_time_steward live read BEFORE confirmation:\n   {read_before!r}\n")

    import main as app_module  # import after schema/env are set up

    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo.local") as client:
        # ── Step 2: parent views the inferred window ────────────────────────
        resp = await client.get(f"/chrono-ritual/{learner_id}/window")
        resp.raise_for_status()
        window_before = resp.json()
        checked_texts.append(("GET /chrono-ritual/window (before)", json.dumps(window_before)))
        print(f"2) GET /chrono-ritual/{learner_id}/window (parent's view, before confirming):")
        print(f"   {json.dumps(window_before, indent=2, default=str)}\n")

        inferred_hour = window_before["inferred_peak_hour"]
        adjusted_hour = (inferred_hour + 2) % 24  # parent adjusts, doesn't just accept as-is

        # ── Step 3: parent confirms/adjusts into a fixed appointment ────────
        resp = await client.post(
            f"/chrono-ritual/{learner_id}/confirm",
            json={
                "confirmed_by": parent_id,
                "hour_of_day": adjusted_hour,
                "days_of_week": [0, 1, 2, 3, 4],  # weekdays, around the tuition batch
            },
        )
        resp.raise_for_status()
        confirm_response = resp.json()
        checked_texts.append(("POST /chrono-ritual/confirm response", json.dumps(confirm_response)))
        print(f"3) POST /chrono-ritual/{learner_id}/confirm — parent adjusts "
              f"{inferred_hour:02d}:00 -> {adjusted_hour:02d}:00, weekdays only:")
        print(f"   {json.dumps(confirm_response, indent=2, default=str)}\n")

        # ── Step 4: confirmed appointment is now stored and retrievable ─────
        resp = await client.get(f"/chrono-ritual/{learner_id}/window")
        resp.raise_for_status()
        window_after = resp.json()
        checked_texts.append(("GET /chrono-ritual/window (after)", json.dumps(window_after)))
        print(f"4) GET /chrono-ritual/{learner_id}/window (after confirmation):")
        print(f"   {json.dumps(window_after, indent=2, default=str)}\n")

        appt = window_after["confirmed_appointment"]
        assert appt is not None, "expected a confirmed appointment to be stored"
        assert appt["hour_of_day"] == adjusted_hour, "stored appointment hour did not match what the parent set"
        assert appt["days_of_week"] == [0, 1, 2, 3, 4], "stored days_of_week did not match what the parent set"
        assert appt["confirmed_by"] == parent_id

    # ── Step 5: downstream readers now prefer the confirmed appointment ────
    async with pool.acquire() as conn:
        read_after = await agent.read(conn, learner_id)
        checked_texts.append(("rhythm_time_steward.read (after confirmation)", read_after))
        print(f"5a) rhythm_time_steward live read AFTER confirmation:\n    {read_after!r}\n")
        assert f"{adjusted_hour:02d}:00" in read_after, "live read did not switch to the confirmed hour"
        assert "parent-set" in read_after

        from modules.lens.contextual import compute as lens_compute
        portrait, _profile = await lens_compute(conn, learner_id)
        sp = portrait.session_pattern
        checked_texts.append(("contextual lens session_pattern.peak_window_label", sp.peak_window_label))
        print(f"5b) Contextual lens session_pattern AFTER confirmation:")
        print(f"    typical_hour={sp.typical_hour}, schedule_confirmed={sp.schedule_confirmed}, "
              f"peak_window_label={sp.peak_window_label!r}\n")
        assert sp.typical_hour == adjusted_hour, "lens did not prefer the confirmed appointment hour"
        assert sp.schedule_confirmed is True

        # Cleanup demo rows so reruns start clean.
        await conn.execute("DELETE FROM learner_state.session_appointment WHERE learner_id = $1", learner_id)
        await conn.execute("DELETE FROM learner_state.rhythm_state WHERE learner_id = $1", learner_id)

    await close_pool()

    # ── Step 6: explicit language check (Invariant 04) ──────────────────────
    findings: list[str] = []
    for label, text in checked_texts:
        _scan(label, text, findings)

    print("=" * 72)
    print("Streak/guilt/punitive language check (Invariant 04, business plan §9):")
    for label, _ in checked_texts:
        print(f"  - scanned: {label}")
    if findings:
        print("FAIL — banned language found:")
        for f in findings:
            print(f"  - {f}")
        return 1

    print("PASS — no streak/guilt/punitive language found in any response text.")
    print("=" * 72)
    print("\nDEMO PASSED: inferred window shown -> parent confirmed/adjusted it -> ")
    print("appointment stored and retrievable -> live reads and guardian-facing")
    print("lens both now prefer the confirmed appointment over the raw inference.")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
