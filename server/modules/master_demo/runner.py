"""
Runs the real, already-verified `server/tests/demo_gap_*.py` scripts on
demand and returns their actual output — this module does not re-implement
or mock any of the 8 gap demos, it invokes the exact code that was used to
prove each PR closed its gap.

Each demo script defines `async def main() -> int | bool | None` guarded by
`if __name__ == "__main__":` at the bottom, so loading it via
importlib (rather than `python3 script.py`) executes every top-level
definition (imports, constants, functions) without auto-running main() —
we call `await mod.main()` explicitly afterward, once, per request.

Two of the eight scripts (demo_gap_consent_fidelity.py,
demo_gap_parent_endpoint_authz.py) only call sys.exit(1) on failure and
otherwise fall through returning None on success — SystemExit is caught
and its code treated as the result; a plain None return with no exception
is treated as a pass, matching those scripts' own success path.
"""
import contextlib
import importlib.util
import io
import sys
import time
import uuid
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[2] / "tests"

FEATURES: dict[str, dict] = {
    "sequence": {
        "pr": 9,
        "ref": "§7.2",
        "title": "Teacher-set content sequence",
        "quote": "The teacher sets the chapter order and the pace in the console; "
                  "Parth's between-class sessions follow it.",
        "script": "demo_gap_teacher_sequence.py",
    },
    "weekly_report": {
        "pr": 10,
        "ref": "§7.3",
        "title": "Parent weekly report, under the teacher's name",
        "quote": "If only one console feature ships in v1, it is this.",
        "script": "demo_gap_parent_weekly_report.py",
    },
    "briefing": {
        "pr": 11,
        "ref": "§7.1",
        "title": "Teacher's Tuesday briefing",
        "quote": "The primary artefact. ... Evidence, not verdict.",
        "script": "demo_gap_teacher_briefing.py",
    },
    "attention": {
        "pr": 12,
        "ref": "Invariant 03",
        "title": "Coarse-attention contract (no camera, no raw signal)",
        "quote": "Never use the camera for monitoring. ... raw signals never leave the phone.",
        "script": "demo_gap_attention_invariant03.py",
    },
    "chrono": {
        "pr": 13,
        "ref": "§8.4",
        "title": "Chrono-learning ritual confirmation",
        "quote": "It is an appointment, not a streak.",
        "script": "demo_gap_chrono_ritual.py",
    },
    "consent": {
        "pr": 14,
        "ref": "Invariant 02",
        "title": "Consent mechanism fidelity",
        "quote": "Never process a child's data without a verified parent.",
        "script": "demo_gap_consent_fidelity.py",
    },
    "transcript": {
        "pr": 15,
        "ref": "Invariant 01",
        "title": "Parent transcript access",
        "quote": "Never hide a word from the parent.",
        "script": "demo_gap_parent_transcript.py",
    },
    "parent_authz": {
        "pr": 16,
        "ref": "Data exposure fix",
        "title": "Parent report/alerts identity check",
        "quote": "Found while building Invariant 01 — the existing endpoints had no "
                  "caller-identity check at all.",
        "script": "demo_gap_parent_endpoint_authz.py",
    },
}


def list_features() -> list[dict]:
    return [
        {"key": key, **{k: v for k, v in meta.items() if k != "script"}}
        for key, meta in FEATURES.items()
    ]


async def run_feature(key: str) -> dict:
    meta = FEATURES.get(key)
    if meta is None:
        return {"key": key, "passed": False, "error": f"unknown feature key {key!r}",
                "output": "", "exit_code": 1, "duration_ms": 0}

    script_path = TESTS_DIR / meta["script"]
    module_name = f"_master_demo_{key}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod

    buf = io.StringIO()
    t0 = time.monotonic()
    exit_code = 0
    error = None
    result = None
    try:
        with contextlib.redirect_stdout(buf):
            spec.loader.exec_module(mod)
            result = await mod.main()
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the demo UI, don't crash the server
        error = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        sys.modules.pop(module_name, None)

    duration_ms = int((time.monotonic() - t0) * 1000)

    if error is not None:
        passed = False
    elif isinstance(result, bool):
        passed = result
    elif isinstance(result, int):
        passed = result == 0
    else:
        passed = exit_code == 0

    return {
        "key": key,
        "passed": bool(passed),
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "output": buf.getvalue(),
        "error": error,
        **{k: v for k, v in meta.items() if k != "script"},
    }
