-- ── Foundation schemas ─────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS foundation;
CREATE SCHEMA IF NOT EXISTS learner_state;
CREATE SCHEMA IF NOT EXISTS curriculum_graph;
CREATE SCHEMA IF NOT EXISTS practice_engine;
CREATE SCHEMA IF NOT EXISTS parent_dashboard;

-- ── Identity ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.identities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        TEXT NOT NULL CHECK (type IN ('child','guardian','teacher')),
    name        TEXT DEFAULT '',
    grade       INT,
    birth_year  INT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS foundation.guardian_links (
    guardian_id   UUID REFERENCES foundation.identities(id) ON DELETE CASCADE,
    child_id      UUID REFERENCES foundation.identities(id) ON DELETE CASCADE,
    consent_given BOOLEAN DEFAULT false,
    consent_ts    TIMESTAMPTZ,
    scope         TEXT[] DEFAULT '{}',
    PRIMARY KEY (guardian_id, child_id)
);

-- ── Event Outbox ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.outbox (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type   TEXT NOT NULL,
    aggregate    TEXT,
    aggregate_id TEXT,
    payload      JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered','failed')),
    created_at   TIMESTAMPTZ DEFAULT now(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbox_pending_idx
    ON foundation.outbox (created_at)
    WHERE status = 'pending';

-- ── Idempotency ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS foundation.idempotency (
    request_id  UUID PRIMARY KEY,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- TTL index for cleanup (rows older than 24h)
CREATE INDEX IF NOT EXISTS idempotency_created_idx
    ON foundation.idempotency (created_at);

-- ── Learner State ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS learner_state.profiles (
    learner_id          TEXT PRIMARY KEY,
    name                TEXT DEFAULT '',
    grade               INT DEFAULT 6,
    sessions            INT DEFAULT 0,
    total_questions     INT DEFAULT 0,
    streak_days         INT DEFAULT 0,
    last_seen           TIMESTAMPTZ,
    last_emotion        TEXT DEFAULT 'neutral',
    engagement_score    REAL DEFAULT 5.0,
    language_ratio      REAL DEFAULT 1.0,
    analogy_scores      JSONB DEFAULT '{}',
    motivational_profile JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learner_state.knowledge (
    learner_id    TEXT NOT NULL,
    concept_id    TEXT NOT NULL,
    exposures     INT DEFAULT 0,
    demonstrations INT DEFAULT 0,
    misconceptions INT DEFAULT 0,
    p_mastery     REAL DEFAULT 0.05,
    last_updated  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (learner_id, concept_id)
);

CREATE TABLE IF NOT EXISTS learner_state.misconception_map (
    id            BIGSERIAL PRIMARY KEY,
    learner_id    TEXT NOT NULL,
    concept_id    TEXT NOT NULL,
    misconception TEXT NOT NULL,
    count         INT DEFAULT 1,
    last_seen     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS misconception_map_learner_idx
    ON learner_state.misconception_map (learner_id, concept_id);

-- ── Episodic Memory — moments worth remembering ────────────────────────────
-- Not a log. Specific meaningful moments: breakthroughs, stated beliefs,
-- deep questions, struggles, connections, moments of awe.
-- Parth uses these to be a mentor who remembers, not a system that processes.

CREATE TABLE IF NOT EXISTS learner_state.episodes (
    id               TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    learner_id       TEXT NOT NULL,
    episode_type     TEXT NOT NULL CHECK (episode_type IN
                         ('breakthrough','belief','question','struggle','connection','awe')),
    verbatim         TEXT NOT NULL,       -- what the child actually said (≤ 200 chars)
    summary          TEXT NOT NULL,       -- one-liner Parth uses to reference this
    concept_ids      TEXT[] DEFAULT '{}',
    pattern_ids      TEXT[] DEFAULT '{}',
    follow_up        TEXT DEFAULT '',     -- question Parth can use to revisit
    referenced_count INT DEFAULT 0,       -- how many times Parth mentioned this
    last_referenced  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS episodes_learner_recent_idx
    ON learner_state.episodes (learner_id, created_at DESC);

CREATE INDEX IF NOT EXISTS episodes_learner_popular_idx
    ON learner_state.episodes (learner_id, referenced_count DESC);

-- ── Curiosity Tracker (session-scoped) ──────────────────────────────────────
-- Stores live curiosity threads per session. Expires at end of day.
-- Never accumulates into a permanent profile — what the child wonders today
-- is theirs today. Parth uses it; no one archives it.

CREATE TABLE IF NOT EXISTS learner_state.curiosity_sessions (
    learner_id   TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    threads_json TEXT NOT NULL DEFAULT '[]',
    updated_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (learner_id, session_id)
);

-- ── Learner Psyche (inferred psychological dimensions) ─────────────────────

CREATE TABLE IF NOT EXISTS learner_state.psyche (
    learner_id          TEXT PRIMARY KEY,
    conscientiousness   REAL DEFAULT 0.5,  -- Big Five: structured, persistent → MBTI J/P
    growth_mindset      REAL DEFAULT 0.5,  -- Dweck: process vs ability attribution
    anxiety             REAL DEFAULT 0.5,  -- Neuroticism: learning anxiety, error-aversion
    depth_preference    REAL DEFAULT 0.5,  -- Need for Cognition: conceptual vs procedural → MBTI N/S
    mastery_orientation REAL DEFAULT 0.5,  -- Achievement Goal Theory: improvement vs comparison
    extroversion        REAL DEFAULT 0.5,  -- Big Five E: social energy, expressiveness → MBTI E/I
    thinking_feeling    REAL DEFAULT 0.5,  -- Big Five A inverse: logic vs values → MBTI T/F
    sample_count        INT  DEFAULT 0,
    last_updated        TIMESTAMPTZ DEFAULT now()
);

-- Add new columns to existing installations
ALTER TABLE learner_state.psyche ADD COLUMN IF NOT EXISTS extroversion     REAL DEFAULT 0.5;
ALTER TABLE learner_state.psyche ADD COLUMN IF NOT EXISTS thinking_feeling REAL DEFAULT 0.5;

-- ── Krishna Oracle — frontier model guidance cache ──────────────────────────

CREATE TABLE IF NOT EXISTS foundation.krishna_guidance (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    trigger     TEXT NOT NULL,     -- 'periodic', 'misconception', 'weekly'
    mbti_type   TEXT,              -- type at time of guidance
    guidance    JSONB NOT NULL DEFAULT '{}',
    applied     BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS krishna_guidance_learner_idx
    ON foundation.krishna_guidance (learner_id, created_at DESC)
    WHERE applied = false;

CREATE TABLE IF NOT EXISTS learner_state.emotion_history (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    emotion     TEXT NOT NULL,
    engagement  REAL NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS emotion_history_learner_idx
    ON learner_state.emotion_history (learner_id, recorded_at DESC);

-- ── Interaction Log ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS learner_state.interactions (
    id           BIGSERIAL PRIMARY KEY,
    learner_id   TEXT NOT NULL,
    request_id   UUID,
    subject      TEXT,
    grade        INT,
    question     TEXT,
    response     TEXT,
    model        TEXT,
    duration_ms  INT,
    misconception TEXT DEFAULT '',
    emotion      TEXT DEFAULT 'neutral',
    engagement   REAL DEFAULT 5.0,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS interactions_learner_idx
    ON learner_state.interactions (learner_id, created_at DESC);

-- ── Curriculum Graph ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS curriculum_graph.concepts (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    grade_min   INT DEFAULT 1,
    grade_max   INT DEFAULT 12,
    description TEXT DEFAULT '',
    video_ids   TEXT[] DEFAULT '{}',
    patterns    TEXT[] DEFAULT '{}'   -- universal structural patterns this concept exhibits
);

ALTER TABLE curriculum_graph.concepts ADD COLUMN IF NOT EXISTS patterns TEXT[] DEFAULT '{}';

-- ── Pattern Library — the universal patterns children discover ───────────────
-- Each pattern appears across radically different scales and domains.
-- When two children find the same pattern in different places, they can meet.

CREATE TABLE IF NOT EXISTS curriculum_graph.pattern_library (
    id          TEXT PRIMARY KEY,      -- 'spiral', 'branching', etc.
    label       TEXT NOT NULL,
    description TEXT NOT NULL,         -- what this pattern IS, in plain language
    examples    TEXT[] DEFAULT '{}',   -- concrete real-world examples across scales
    scales      TEXT[] DEFAULT '{}'    -- 'cosmic' | 'planetary' | 'biological' | 'atomic' | 'mathematical'
);

-- ── Pattern Encounters — what has each child discovered ─────────────────────
-- Session-agnostic. A child "owns" a pattern encounter when they engage with
-- a concept exhibiting that pattern. This is the hook for the future social feature:
-- find another child who found the same pattern from a different domain.

CREATE TABLE IF NOT EXISTS learner_state.pattern_encounters (
    id              BIGSERIAL PRIMARY KEY,
    learner_id      TEXT NOT NULL,
    pattern_id      TEXT NOT NULL REFERENCES curriculum_graph.pattern_library(id),
    concept_id      TEXT NOT NULL,          -- which concept revealed this pattern
    domain          TEXT NOT NULL,          -- 'mathematics' | 'science' | 'social_science'
    discovery_note  TEXT DEFAULT '',        -- what the child said when they found it (verbatim snippet)
    engagement      REAL DEFAULT 5.0,       -- engagement at moment of discovery
    discovered_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pattern_encounters_learner_idx
    ON learner_state.pattern_encounters (learner_id, pattern_id);

CREATE INDEX IF NOT EXISTS pattern_encounters_pattern_idx
    ON learner_state.pattern_encounters (pattern_id, discovered_at DESC);

CREATE TABLE IF NOT EXISTS curriculum_graph.concept_edges (
    from_id TEXT NOT NULL REFERENCES curriculum_graph.concepts(id),
    to_id   TEXT NOT NULL REFERENCES curriculum_graph.concepts(id),
    type    TEXT NOT NULL CHECK (type IN ('prerequisite','co-requisite','leads-to')),
    PRIMARY KEY (from_id, to_id, type)
);

CREATE TABLE IF NOT EXISTS curriculum_graph.ka_videos (
    video_id         TEXT NOT NULL,
    concept_id       TEXT NOT NULL REFERENCES curriculum_graph.concepts(id),
    title            TEXT DEFAULT '',
    transcript_chars INT DEFAULT 0,
    embedded         BOOLEAN DEFAULT false,
    fetched_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (video_id, concept_id)
);

-- ── Practice Engine ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS practice_engine.cards (
    learner_id    TEXT NOT NULL,
    concept_id    TEXT NOT NULL,
    next_review   TIMESTAMPTZ DEFAULT now(),
    interval_days REAL DEFAULT 1.0,
    ease_factor   REAL DEFAULT 2.5,
    repetitions   INT DEFAULT 0,
    PRIMARY KEY (learner_id, concept_id)
);

CREATE TABLE IF NOT EXISTS practice_engine.answers (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    concept_id  TEXT NOT NULL,
    correct     BOOLEAN NOT NULL,
    quality     INT DEFAULT 3 CHECK (quality BETWEEN 0 AND 5),
    answered_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS answers_learner_idx
    ON practice_engine.answers (learner_id, concept_id, answered_at DESC);

-- ── Parent Dashboard ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS parent_dashboard.reports (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    guardian_id UUID,
    report_type TEXT NOT NULL DEFAULT 'weekly',
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parent_dashboard.alerts (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    message     TEXT NOT NULL,
    acknowledged BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ── Gap 6: Emotional state TTL — session-scoped misconception tracking ───────

ALTER TABLE learner_state.knowledge ADD COLUMN IF NOT EXISTS last_misconception_session TEXT DEFAULT '';
ALTER TABLE learner_state.knowledge ADD COLUMN IF NOT EXISTS session_misconception_count INT DEFAULT 0;

-- ── Gap 7: Pilot metrics instrumentation ────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS metrics;

CREATE TABLE IF NOT EXISTS metrics.sessions (
    id                     BIGSERIAL,
    learner_id             TEXT NOT NULL,
    session_date           DATE NOT NULL DEFAULT CURRENT_DATE,
    messages_sent          INT DEFAULT 0,
    concepts_covered       TEXT[] DEFAULT '{}',
    misconceptions_detected INT DEFAULT 0,
    model_calls            INT DEFAULT 0,
    -- Cost tracking: gemma3:12b ≈ 0 (local), claude ≈ $0.000025/token
    krishna_tokens         INT DEFAULT 0,
    harmful_flag           BOOLEAN DEFAULT FALSE,
    session_start          TIMESTAMPTZ DEFAULT now(),
    session_end            TIMESTAMPTZ,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS metrics_sessions_learner_date
    ON metrics.sessions (learner_id, session_date);

CREATE TABLE IF NOT EXISTS metrics.pilot_gates (
    learner_id   TEXT NOT NULL,
    gate         TEXT NOT NULL,  -- 'activation', 'd7_retention', 'w4_gain', 'harmful_ai'
    value        REAL,
    passed       BOOLEAN,
    evaluated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (learner_id, gate)
);

-- ── Open-loop generator — planted wonders that bring children back ────────────

CREATE TABLE IF NOT EXISTS learner_state.open_loops (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    learner_id  TEXT NOT NULL,
    question    TEXT NOT NULL,
    concept_ids TEXT[] DEFAULT '{}',
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','closed','expired')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    closed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS open_loops_learner_open_idx
    ON learner_state.open_loops (learner_id, created_at DESC)
    WHERE status = 'open';
