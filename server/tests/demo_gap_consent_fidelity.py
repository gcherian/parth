#!/usr/bin/env python3
"""
Standalone demo for Invariant 02 (business plan Sec. 9) — consent mechanism
fidelity. Run against the real shared dev Postgres DB, no port binding:

    python3 server/tests/demo_gap_consent_fidelity.py

What this shows, with explicit PASS/FAIL lines:

  1. foundation.identity.grant_pilot_consent() — the synthetic-guardian pilot
     bypass — refuses to run (raises SyntheticConsentDisabledError, does not
     silently no-op or silently succeed) unless ALLOW_SYNTHETIC_CONSENT is
     explicitly enabled. Before this fix it was reachable unconditionally,
     including via the live /learner/consent endpoint in main.py.
  2. It succeeds once the flag is explicitly set, for a demo child ID
     prefixed demo-consent- so it never collides with other agents' rows in
     this shared DB.
  3. The resulting foundation.guardian_links row carries an explicit
     consent_method='synthetic_pilot' — and, for contrast, a second demo
     child is walked through the REAL OTP-verified consent path
     (foundation.consent_vc.initiate_consent / complete_consent — the same
     functions modules/iam/routes.py's /consent/request + /consent/verify
     call in production) whose row carries consent_method='otp'. The two
     values are asserted to differ — the system never claims
     DigiLocker-equivalence (or even OTP-equivalence) for a synthetic grant.
  4. foundation.consent_vc.verify_via_digilocker() — the DigiLocker contract
     stub — raises NotImplementedError, so the missing mechanism is visible
     in the code, not silently absent.

All demo rows use identities that only exist for this run; no real learner
data is touched.
"""
import asyncio
import os
import sys
import uuid as _uuid
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

# Demo-visible OTP (skips real SMTP delivery) — see foundation/otp.py. Never
# set this in production; it's exactly the flag main.py's investor-demo mode
# uses for /iam/consent/request.
os.environ.setdefault("DEMO_OTP_FORCE", "true")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(override=False)

from foundation import identity  # noqa: E402
from foundation import consent_vc  # noqa: E402
from foundation import did as did_module  # noqa: E402
from foundation.db import get_pool, close_pool, apply_schema  # noqa: E402
from foundation.iam_schema import apply_iam_schema  # noqa: E402
from foundation.otp import _demo_otp_store  # noqa: E402

results: list[bool] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    results.append(bool(condition))


async def main() -> None:
    await apply_schema()
    await apply_iam_schema()

    demo_child_synth = _uuid.uuid4()
    demo_child_otp = _uuid.uuid4()
    demo_guardian_otp = _uuid.uuid4()

    print("=== Invariant 02 — consent mechanism fidelity ===\n")

    # ── Part 1: synthetic bypass refuses without the flag ──────────────────
    print("-- Part 1: grant_pilot_consent() refuses without ALLOW_SYNTHETIC_CONSENT --")
    identity.Config.ALLOW_SYNTHETIC_CONSENT = False

    reg_ok = await identity.register_pilot_learner(
        str(demo_child_synth), "demo-consent-child-synth", 6,
    )
    check("register_pilot_learner() created the demo child", reg_ok)

    refused, error_message = False, ""
    try:
        await identity.grant_pilot_consent(str(demo_child_synth))
    except identity.SyntheticConsentDisabledError as exc:
        refused, error_message = True, str(exc)
    check(
        "grant_pilot_consent() raised SyntheticConsentDisabledError with the flag unset",
        refused,
    )
    print(f"    actual error: {error_message}")

    still_denied = not await identity.check_consent(
        str(demo_child_synth), identity.SCOPE_AI_INTERACTION,
    )
    check("check_consent() still denies — the refused call had no side effect", still_denied)

    # ── Part 2: succeeds once explicitly enabled ────────────────────────────
    print("\n-- Part 2: grant_pilot_consent() succeeds once ALLOW_SYNTHETIC_CONSENT=true --")
    identity.Config.ALLOW_SYNTHETIC_CONSENT = True

    granted = await identity.grant_pilot_consent(str(demo_child_synth))
    check("grant_pilot_consent() returned True with the flag explicitly enabled", granted)

    now_allowed = await identity.check_consent(
        str(demo_child_synth), identity.SCOPE_AI_INTERACTION,
    )
    check("check_consent() now allows ai_interaction for the demo child", now_allowed)

    # ── Part 3: consent_method distinguishes synthetic from real OTP ───────
    print("\n-- Part 3: consent_method distinguishes mechanisms --")
    pool = await get_pool()
    async with pool.acquire() as conn:
        synth_row = await conn.fetchrow(
            "SELECT consent_method FROM foundation.guardian_links WHERE child_id = $1",
            demo_child_synth,
        )
    synth_method = synth_row["consent_method"] if synth_row else None
    check(
        "synthetic grant recorded consent_method='synthetic_pilot'",
        synth_method == "synthetic_pilot",
    )
    print(f"    guardian_links.consent_method = {synth_method!r}")

    print("\n-- Part 3b: real OTP-verified consent path, for contrast --")
    await identity.register_pilot_learner(str(demo_child_otp), "demo-consent-child-otp", 6)

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO foundation.identities (id, type, name)
               VALUES ($1, 'guardian', $2) ON CONFLICT (id) DO NOTHING""",
            demo_guardian_otp, "demo-consent-guardian",
        )
        await conn.execute(
            """INSERT INTO foundation.guardian_links (guardian_id, child_id, consent_given, scope)
               VALUES ($1, $2, false, '{}') ON CONFLICT (guardian_id, child_id) DO NOTHING""",
            demo_guardian_otp, demo_child_otp,
        )
    guardian_did, _ = await did_module.create_did_for_identity(demo_guardian_otp, save_private=True)

    token_id = await consent_vc.initiate_consent(
        guardian_did=guardian_did,
        child_id=demo_child_otp,
        scope=["ai_interaction", "learner_data"],
        guardian_email="demo-consent-guardian@example.com",
    )
    otp_code = _demo_otp_store.get(str(token_id))
    check("a real OTP was issued for the guardian (DEMO_OTP_FORCE, no SMTP needed)", bool(otp_code))

    vc = await consent_vc.complete_consent(
        guardian_did=guardian_did,
        child_id=demo_child_otp,
        scope=["ai_interaction", "learner_data"],
        otp_token_id=token_id,
        submitted_otp=otp_code,
    )
    check("complete_consent() issued a ParentalConsentVC after real OTP verification", bool(vc))

    async with pool.acquire() as conn:
        otp_row = await conn.fetchrow(
            "SELECT consent_method FROM foundation.guardian_links WHERE child_id = $1",
            demo_child_otp,
        )
    otp_method = otp_row["consent_method"] if otp_row else None
    check("real OTP-verified grant recorded consent_method='otp'", otp_method == "otp")
    print(f"    guardian_links.consent_method = {otp_method!r}")

    check(
        "synthetic and OTP-verified rows carry DIFFERENT consent_method values "
        f"({synth_method!r} != {otp_method!r})",
        synth_method is not None and otp_method is not None and synth_method != otp_method,
    )

    # ── Part 4: DigiLocker is an honest stub, not a silent absence ─────────
    print("\n-- Part 4: verify_via_digilocker() is a declared stub, not silently absent --")
    digilocker_raised = False
    try:
        await consent_vc.verify_via_digilocker(
            guardian_did=guardian_did,
            child_id=demo_child_otp,
            digilocker_auth_code="fake-code-not-a-real-integration",
            scope=["ai_interaction"],
        )
    except NotImplementedError as exc:
        digilocker_raised = True
        print(f"    actual error: {exc}")
    check("verify_via_digilocker() raises NotImplementedError (honest stub, not silent)", digilocker_raised)

    await close_pool()

    print("\n=== Summary ===")
    total, passed = len(results), sum(results)
    print(f"{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
