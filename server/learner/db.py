import sqlite3
from pathlib import Path

from config import Config

DB_PATH = Config.DATA_DIR / "parth.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        # Core tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learners (
                id                   TEXT PRIMARY KEY,
                name                 TEXT DEFAULT '',
                grade                INTEGER DEFAULT 6,
                sessions             INTEGER DEFAULT 0,
                total_questions      INTEGER DEFAULT 0,
                weak_topics          TEXT DEFAULT '[]',
                misconceptions       TEXT DEFAULT '[]',
                last_seen            TEXT,
                streak_days          INTEGER DEFAULT 0,
                -- Tier 1 learner model columns
                knowledge_state      TEXT DEFAULT '{}',
                misconception_map    TEXT DEFAULT '{}',
                motivational_profile TEXT DEFAULT '{}',
                last_emotion         TEXT DEFAULT 'neutral',
                engagement_score     REAL DEFAULT 5.0,
                language_ratio       REAL DEFAULT 1.0,
                analogy_scores       TEXT DEFAULT '{}'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                learner_id    TEXT,
                ts            TEXT,
                subject       TEXT,
                grade         INTEGER,
                question      TEXT,
                response      TEXT,
                model         TEXT,
                duration_ms   INTEGER,
                misconception TEXT DEFAULT '',
                emotion       TEXT DEFAULT 'neutral',
                engagement    INTEGER DEFAULT 5
            )
        """)

        # Add new columns to existing DBs that were created before this schema
        _migrate(conn)


def _migrate(conn: sqlite3.Connection):
    """Idempotent: add any missing columns to the learners / interactions tables."""
    learner_cols = {row[1] for row in conn.execute("PRAGMA table_info(learners)")}
    _add_if_missing = [
        ("knowledge_state",      "TEXT DEFAULT '{}'"),
        ("misconception_map",    "TEXT DEFAULT '{}'"),
        ("motivational_profile", "TEXT DEFAULT '{}'"),
        ("last_emotion",         "TEXT DEFAULT 'neutral'"),
        ("engagement_score",     "REAL DEFAULT 5.0"),
        ("language_ratio",       "REAL DEFAULT 1.0"),
        ("analogy_scores",       "TEXT DEFAULT '{}'"),
    ]
    for col, definition in _add_if_missing:
        if col not in learner_cols:
            conn.execute(f"ALTER TABLE learners ADD COLUMN {col} {definition}")

    interaction_cols = {row[1] for row in conn.execute("PRAGMA table_info(interactions)")}
    for col, definition in [("emotion", "TEXT DEFAULT 'neutral'"),
                             ("engagement", "INTEGER DEFAULT 5")]:
        if col not in interaction_cols:
            conn.execute(f"ALTER TABLE interactions ADD COLUMN {col} {definition}")
