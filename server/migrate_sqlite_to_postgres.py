"""
One-shot migration: copies existing SQLite learner data into Postgres.
Run ONCE after Postgres is up and schema is applied.

Usage:
    python migrate_sqlite_to_postgres.py
"""
import asyncio
import json
import sqlite3
from pathlib import Path

import asyncpg

SQLITE_PATH = Path.home() / ".parth" / "parth.db"
PG_DSN = "postgresql://parth:parth_dev@localhost:5432/parth"


def _read_sqlite() -> tuple[list[dict], list[dict]]:
    if not SQLITE_PATH.exists():
        print(f"SQLite DB not found at {SQLITE_PATH} — nothing to migrate.")
        return [], []

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row

    learners = [dict(r) for r in conn.execute("SELECT * FROM learners").fetchall()]
    try:
        interactions = [
            dict(r) for r in conn.execute("SELECT * FROM interactions").fetchall()
        ]
    except Exception:
        interactions = []

    conn.close()
    print(f"  SQLite: {len(learners)} learners, {len(interactions)} interactions")
    return learners, interactions


async def _migrate(learners: list[dict], interactions: list[dict]):
    pool = await asyncpg.create_pool(PG_DSN)

    async with pool.acquire() as conn:
        for row in learners:
            # Parse JSON columns that were stored as strings in SQLite
            def _j(val, default):
                if not val:
                    return default
                try:
                    return json.loads(val) if isinstance(val, str) else val
                except Exception:
                    return default

            await conn.execute(
                """
                INSERT INTO learner_state.profiles
                    (learner_id, name, grade, sessions, total_questions,
                     streak_days, last_emotion, engagement_score, language_ratio,
                     analogy_scores, motivational_profile)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (learner_id) DO NOTHING
                """,
                row["id"],
                row.get("name", ""),
                row.get("grade", 6),
                row.get("sessions", 0),
                row.get("total_questions", 0),
                row.get("streak_days", 0),
                row.get("last_emotion", "neutral"),
                float(row.get("engagement_score", 5.0)),
                float(row.get("language_ratio", 1.0)),
                json.dumps(_j(row.get("analogy_scores", "{}"), {})),
                json.dumps(_j(row.get("motivational_profile", "{}"), {})),
            )

            # Migrate knowledge_state JSON blob into normalised rows
            ks = _j(row.get("knowledge_state", "{}"), {})
            for concept_id, data in ks.items():
                await conn.execute(
                    """
                    INSERT INTO learner_state.knowledge
                        (learner_id, concept_id, exposures, demonstrations, misconceptions, p_mastery)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (learner_id, concept_id) DO NOTHING
                    """,
                    row["id"], concept_id,
                    int(data.get("exposures", 0)),
                    int(data.get("demonstrations", 0)),
                    int(data.get("misconceptions", 0)),
                    float(data.get("p_mastery", 0.05)),
                )

            # Migrate misconception_map JSON blob
            mm = _j(row.get("misconception_map", "{}"), {})
            for concept_id, misc_text in mm.items():
                if misc_text:
                    await conn.execute(
                        """
                        INSERT INTO learner_state.misconception_map
                            (learner_id, concept_id, misconception)
                        VALUES ($1,$2,$3)
                        """,
                        row["id"], concept_id, str(misc_text)[:500],
                    )

        print(f"  Migrated {len(learners)} learner profiles.")

        for row in interactions:
            await conn.execute(
                """
                INSERT INTO learner_state.interactions
                    (learner_id, subject, grade, question, response,
                     model, duration_ms, misconception, emotion, engagement)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                row.get("learner_id", ""),
                row.get("subject", ""),
                int(row.get("grade", 6)),
                (row.get("question") or "")[:1000],
                (row.get("response") or "")[:2000],
                row.get("model", ""),
                int(row.get("duration_ms", 0)),
                row.get("misconception", ""),
                row.get("emotion", "neutral"),
                float(row.get("engagement", 5)),
            )
        print(f"  Migrated {len(interactions)} interactions.")

    await pool.close()


async def main():
    print("Parth SQLite → Postgres migration")
    learners, interactions = _read_sqlite()
    if not learners and not interactions:
        return
    print("Connecting to Postgres...")
    await _migrate(learners, interactions)
    print("Done. You can now start the server with Postgres.")


if __name__ == "__main__":
    asyncio.run(main())
