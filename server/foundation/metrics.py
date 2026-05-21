"""Lightweight session metrics — answers pilot gate questions."""
from datetime import date, timedelta

from foundation.observability import get_logger

log = get_logger("foundation.metrics")


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


async def compute_pilot_gates(conn, learner_id: str) -> dict:
    """
    Compute and store pilot gate metrics:
    - activation:   completed session 1 (messages_sent >= 3)
    - d7_retention: returned on day 7 after first session
    - w4_gain:      average p_mastery increase from week 1 to week 4
    - harmful_ai:   any harmful_flag=true sessions?
    Returns dict of gate results, also persists to metrics.pilot_gates.
    """
    gates: dict = {}

    try:
        # ── activation ─────────────────────────────────────────────────────
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
        if first_session:
            activation_passed = first_session["messages_sent"] >= 3
            gates["activation"] = {
                "value": float(first_session["messages_sent"]),
                "passed": activation_passed,
            }
            first_date = first_session["session_date"]

            # ── d7_retention ───────────────────────────────────────────────
            day7 = first_date + timedelta(days=7)
            d7_row = await conn.fetchrow(
                """
                SELECT 1 FROM metrics.sessions
                WHERE learner_id = $1 AND session_date = $2
                """,
                learner_id, day7,
            )
            gates["d7_retention"] = {
                "value": 1.0 if d7_row else 0.0,
                "passed": d7_row is not None,
            }

            # ── w4_gain ────────────────────────────────────────────────────
            # Compare average p_mastery of first-week concepts vs week-4 state
            week1_end = first_date + timedelta(days=7)
            week4_start = first_date + timedelta(days=21)
            week4_end = first_date + timedelta(days=28)

            # Week 1 concepts covered
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
                # Current mastery of those concepts
                mastery_rows = await conn.fetch(
                    """
                    SELECT AVG(p_mastery) AS avg_mastery
                    FROM learner_state.knowledge
                    WHERE learner_id = $1
                      AND concept_id = ANY($2::text[])
                    """,
                    learner_id, w1_concepts,
                )
                current_avg = float(mastery_rows[0]["avg_mastery"] or 0.05)
                # Baseline: assume 0.05 at start (no prior data for week-1 snapshot)
                w4_gain = round(current_avg - 0.05, 3)
                gates["w4_gain"] = {
                    "value": w4_gain,
                    "passed": w4_gain >= 0.15,  # meaningful gain threshold
                }
            else:
                gates["w4_gain"] = {"value": 0.0, "passed": False}
        else:
            gates["activation"] = {"value": 0.0, "passed": False}
            gates["d7_retention"] = {"value": 0.0, "passed": False}
            gates["w4_gain"] = {"value": 0.0, "passed": False}

        # ── harmful_ai ─────────────────────────────────────────────────────
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
            "value": float(harmful_count),
            "passed": harmful_count == 0,
        }

        # ── Persist results to pilot_gates ────────────────────────────────
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
