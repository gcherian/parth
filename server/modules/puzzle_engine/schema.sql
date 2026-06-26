-- Puzzle Engine schema
-- Applied via foundation/db.py apply_schema()

CREATE SCHEMA IF NOT EXISTS puzzle_engine;

CREATE TABLE IF NOT EXISTS puzzle_engine.responses (
    id              BIGSERIAL PRIMARY KEY,
    learner_id      TEXT NOT NULL,
    puzzle_id       TEXT NOT NULL,
    thinker_id      TEXT NOT NULL,
    sphere          TEXT NOT NULL,
    level           TEXT NOT NULL,          -- beginner | intermediate | advanced
    response_text   TEXT DEFAULT '',
    time_seconds    INTEGER DEFAULT 0,      -- seconds spent before submitting
    quality         SMALLINT DEFAULT 0,     -- 0=blank 1=attempt 2=insight 3=deep
    reached_deeper  BOOLEAN DEFAULT FALSE,  -- attempted go_deeper
    misconception   TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS puzzle_responses_learner
    ON puzzle_engine.responses (learner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS puzzle_engine.sphere_affinity (
    learner_id      TEXT NOT NULL,
    sphere          TEXT NOT NULL,
    affinity        REAL DEFAULT 5.0,   -- EMA score 1-10
    attempts        INTEGER DEFAULT 0,
    avg_quality     REAL DEFAULT 0.0,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (learner_id, sphere)
);

CREATE TABLE IF NOT EXISTS puzzle_engine.learner_state (
    learner_id          TEXT PRIMARY KEY,
    last_puzzle_id      TEXT DEFAULT '',
    last_sphere         TEXT DEFAULT '',
    consecutive_sphere  INTEGER DEFAULT 0,
    total_puzzles       INTEGER DEFAULT 0,
    onboarding_done     BOOLEAN DEFAULT FALSE,
    telos               TEXT DEFAULT '',
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS puzzle_engine.portraits (
    learner_id      TEXT PRIMARY KEY,
    portrait_json   TEXT NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS puzzle_engine.register_states (
    learner_id      TEXT PRIMARY KEY,
    state_json      TEXT NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- SAINT-format interaction log for future knowledge tracing model training
CREATE TABLE IF NOT EXISTS puzzle_engine.kt_interactions (
    id              BIGSERIAL PRIMARY KEY,
    learner_id      TEXT NOT NULL,
    puzzle_id       TEXT NOT NULL,
    concept_tags    TEXT[] NOT NULL DEFAULT '{}',  -- from silent_lesson parsing
    response_quality SMALLINT NOT NULL,             -- 0-3
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    hint_used       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS kt_learner_seq
    ON puzzle_engine.kt_interactions (learner_id, created_at ASC);
