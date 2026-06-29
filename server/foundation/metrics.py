"""Lightweight session metrics — answers pilot gate questions.

Six gates, matching the deck:
  activation       — completed session 1 (≥3 messages)
  d7_retention     — returned on day 7 after first session
  d14_retention    — returned on day 14 (confirms habit, not luck)
  w4_gain          — +10pp p_mastery gain from pretest baseline to week-4
  guardian_engaged — parent/guardian accessed dashboard at least once
  harmful_ai       — zero harmful_flag sessions

Pretest baseline: call record_pretest_baseline() at or before the first
session. Without it, w4_gain falls back to grade-appropriate BKT priors
(0.10) rather than the deck's previous false 0.05 assumption.
"""
from datetime import date, timedelta

from foundation.observability import get_logger

log = get_logger("foundation.metrics")

# BKT default prior per grade band — used only when no real baseline is stored.
_GRADE_PRIOR = {6: 0.10, 7: 0.11, 8: 0.12}
_DEFAULT_PRIOR = 0.10


async def record_interaction(
    conn,
    learner_id: str,
    session_date: date,
    concepts: list,
    had_misconception: bool,
    harmful: bool = False,
) -> None:
    """
    Upsert today's session row, incrementing counters.
    Uses INSERT ... ON CONFLICT (learner_id, session_date) DO UPDATE.
    Never raises — all errors are logged and swallowed.
    """
    try:
        concepts_arr = list(concepts) if concepts else []
        await conn.execute(
            """
            INSERT INTO metrics.sessions
                (learner_id, session_date, messages_sent, concepts_covered,
                 misconceptions_detected, model_calls, harmful_flag)
            VALUES ($1, $2, 1, $3::text[], $4::int, 1, $5)
            ON CONFLICT (learner_id, session_date) DO UPDATE
                SET messages_sent           = metrics.sessions.messages_sent + 1,
                    concepts_covered        = (
                        SELECT array_agg(DISTINCT elem)
                        FROM unnest(
                            metrics.sessions.concepts_covered || $3::text[]
                        ) AS elem
                    ),
                    misconceptions_detected = metrics.sessions.misconceptions_detected + $4::int,
                    model_calls             = metrics.sessions.model_calls + 1,
                    harmful_flag            = metrics.sessions.harmful_flag OR $5,
                    session_end             = now()
            """,
            learner_id,
            session_date,
            concepts_arr,
            1 if had_misconception else 0,
            harmful,
        )
    except Exception as exc:
        log.warning("metrics_record_failed", learner_id=learner_id, error=str(exc))


async def record_pretest_baseline(conn, learner_id: str) -> None:
    """
    Snapshot the learner's current average p_mastery into metrics.learner_baselines.
    Call once — at onboarding or before the first real session — so w4_gain
    has a real starting point. Idempotent: subsequent calls do nothing.
    """
    try:
        row = await conn.fetchrow(
            """
            SELECT AVG(p_mastery) AS avg_m, COUNT(*) AS cnt
            FROM learner_state.knowledge
            WHERE learner_id = $1
            """,
            learner_id,
        )
        avg_m = float(row["avg_m"] or 0.0)
        cnt   = int(row["cnt"] or 0)
        await conn.execute(
            """
            INSERT INTO metrics.learner_baselines (learner_id, avg_mastery, concept_count)
            VALUES ($1, $2, $3)
            ON CONFLICT (learner_id) DO NOTHING
            """,
            learner_id, avg_m, cnt,
        )
        log.info("pretest_baseline_recorded", learner_id=learner_id,
                 avg_mastery=avg_m, concepts=cnt)
    except Exception as exc:
        log.warning("pretest_baseline_failed", learner_id=learner_id, error=str(exc))


async def _get_pretest_baseline(conn, learner_id: str, grade: int = 6) -> float:
    """Return stored baseline, or a grade-appropriate BKT prior if none stored."""
    try:
        row = await conn.fetchrow(
            "SELECT avg_mastery FROM metrics.learner_baselines WHERE learner_id = $1",
            learner_id,
        )
        if row and row["avg_mastery"] is not None:
            return float(row["avg_mastery"])
    except Exception:
        pass
    return _GRADE_PRIOR.get(grade, _DEFAULT_PRIOR)


async def compute_pilot_gates(conn, learner_id: str) -> dict:
    """
    Compute and store all six pilot gate metrics.
    Returns dict of gate results; also persists to metrics.pilot_gates.
    """
    gates: dict = {}

    try:
        # ── Fetch learner grade for baseline fallback ─────────────────────────
        grade_row = await conn.fetchrow(
            "SELECT grade FROM learner_state.profiles WHERE learner_id = $1",
            learner_id,
        )
        grade = int(grade_row["grade"]) if grade_row else 6

        # ── 1. activation ─────────────────────────────────────────────────────
        first_session = await conn.fetchrow(
            """
            SELECT session_date, messages_sent
            FROM metrics.sessions
            WHERE learner_id = $1
            ORDER BY session_date ASC
            LIMIT 1
            """,
            learner_id,
        )

        if not first_session:
            for g in ("activation", "d7_retention", "d14_retention", "w4_gain"):
                gates[g] = {"value": 0.0, "passed": False}
        else:
            first_date = first_session["session_date"]

            gates["activation"] = {
                "value": float(first_session["messages_sent"]),
                "passed": first_session["messages_sent"] >= 3,
            }

            # ── 2. d7_retention ───────────────────────────────────────────────
            day7 = first_date + timedelta(days=7)
            d7_row = await conn.fetchrow(
                "SELECT 1 FROM metrics.sessions WHERE learner_id=$1 AND session_date=$2",
                learner_id, day7,
            )
            gates["d7_retention"] = {
                "value": 1.0 if d7_row else 0.0,
                "passed": d7_row is not None,
            }

            # ── 3. d14_retention ──────────────────────────────────────────────
            day14 = first_date + timedelta(days=14)
            d14_row = await conn.fetchrow(
                "SELECT 1 FROM metrics.sessions WHERE learner_id=$1 AND session_date=$2",
                learner_id, day14,
            )
            gates["d14_retention"] = {
                "value": 1.0 if d14_row else 0.0,
                "passed": d14_row is not None,
            }

            # ── 4. w4_gain ────────────────────────────────────────────────────
            week1_end = first_date + timedelta(days=7)
            w1_rows = await conn.fetch(
                """
                SELECT DISTINCT unnest(concepts_covered) AS concept_id
                FROM metrics.sessions
                WHERE learner_id = $1
                  AND session_date BETWEEN $2 AND $3
                """,
                learner_id, first_date, week1_end,
            )
            w1_concepts = [r["concept_id"] for r in w1_rows]

            if w1_concepts:
                mastery_row = await conn.fetchrow(
                    """
                    SELECT AVG(p_mastery) AS avg_mastery
                    FROM learner_state.knowledge
                    WHERE learner_id = $1 AND concept_id = ANY($2::text[])
                    """,
                    learner_id, w1_concepts,
                )
                current_avg = float(mastery_row["avg_mastery"] or 0.0)
                baseline    = await _get_pretest_baseline(conn, learner_id, grade)
                w4_gain     = round(current_avg - baseline, 3)
                gates["w4_gain"] = {
                    "value":          w4_gain,
                    "passed":         w4_gain >= 0.10,
                    "baseline_source": "stored" if baseline not in _GRADE_PRIOR.values()
                                       else "grade_prior",
                }
            else:
                gates["w4_gain"] = {"value": 0.0, "passed": False,
                                    "baseline_source": "no_data"}

        # ── 5. guardian_engaged ───────────────────────────────────────────────
        guardian_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM parent_dashboard.views WHERE learner_id = $1",
            learner_id,
        )
        g_count = int(guardian_row["cnt"]) if guardian_row else 0
        gates["guardian_engaged"] = {
            "value":  float(g_count),
            "passed": g_count >= 1,
        }

        # ── 6. harmful_ai ─────────────────────────────────────────────────────
        harmful_row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS cnt
            FROM metrics.sessions
            WHERE learner_id = $1 AND harmful_flag = true
            """,
            learner_id,
        )
        harmful_count = int(harmful_row["cnt"]) if harmful_row else 0
        gates["harmful_ai"] = {
            "value":  float(harmful_count),
            "passed": harmful_count == 0,
        }

        # ── Persist all gates ─────────────────────────────────────────────────
        for gate_name, result in gates.items():
            await conn.execute(
                """
                INSERT INTO metrics.pilot_gates (learner_id, gate, value, passed, evaluated_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (learner_id, gate) DO UPDATE
                    SET value        = $3,
                        passed       = $4,
                        evaluated_at = now()
                """,
                learner_id,
                gate_name,
                result["value"],
                result["passed"],
            )

    except Exception as exc:
        log.warning("pilot_gates_failed", learner_id=learner_id, error=str(exc))

    return gates
