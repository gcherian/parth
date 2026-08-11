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

-- Add new columns to existing installations
ALTER TABLE foundation.identities ADD COLUMN IF NOT EXISTS school_id TEXT;

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

-- Unused by anything yet — added ahead of need because it's cheap now and
-- expensive to retrofit once outbox rows accumulate without it. This is the
-- data shape the future Trust Plane purpose-limitation check will need (see
-- ParthOS/docs/IMPLEMENTATION_ROADMAP.md Track A item 4).
ALTER TABLE foundation.outbox ADD COLUMN IF NOT EXISTS purpose TEXT;

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

-- 'observation' — a child volunteering something they noticed in real
-- life (modules/observation_engine), distinct from the other six types
-- which are all passively detected from chat text by episodes.detect_type().
-- Idempotent re-apply: drop-then-recreate rather than IF NOT EXISTS,
-- since Postgres has no ADD CONSTRAINT IF NOT EXISTS for CHECK.
ALTER TABLE learner_state.episodes DROP CONSTRAINT IF EXISTS episodes_episode_type_check;
ALTER TABLE learner_state.episodes ADD CONSTRAINT episodes_episode_type_check
    CHECK (episode_type IN
        ('breakthrough','belief','question','struggle','connection','awe','observation'));

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

-- ── Per-child agent configuration ────────────────────────────────────────────
-- Each row overrides one agent's defaults for one child.
-- Agents fall back to global Config.* constants when no row exists.
-- set_by tracks provenance: system defaults, guardian form, BMAD onboarding, teacher.

CREATE TABLE IF NOT EXISTS learner_state.child_agent_config (
    learner_id   TEXT        NOT NULL,
    agent_name   TEXT        NOT NULL,
    config       JSONB       NOT NULL DEFAULT '{}',
    set_by       TEXT        NOT NULL DEFAULT 'system'
                             CHECK (set_by IN ('system','guardian','bmad_onboarding','teacher')),
    notes        TEXT        DEFAULT '',   -- guardian-visible rationale
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (learner_id, agent_name)
);

-- Global per-child settings that apply across all agents (exam mode, response length, etc.)
CREATE TABLE IF NOT EXISTS learner_state.child_global_config (
    learner_id        TEXT        NOT NULL PRIMARY KEY,
    exam_prep_mode    BOOLEAN     NOT NULL DEFAULT false,
    exam_date         DATE,                              -- null = no exam pressure
    max_response_words INT        NOT NULL DEFAULT 200
                                  CHECK (max_response_words BETWEEN 50 AND 500),
    session_persona   TEXT        NOT NULL DEFAULT 'auto'
                                  CHECK (session_persona IN ('auto','encouraging','socratic','direct','playful')),
    set_by            TEXT        NOT NULL DEFAULT 'system',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Guardian onboarding conversation state.
-- Stores raw responses from the BMAD-style onboarding; once complete,
-- the onboarding module writes the derived configs into child_agent_config.

CREATE TABLE IF NOT EXISTS learner_state.onboarding (
    learner_id      TEXT        NOT NULL PRIMARY KEY,
    guardian_id     TEXT,                              -- links to foundation.identities
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','in_progress','complete')),
    responses       JSONB       NOT NULL DEFAULT '{}', -- raw guardian answers keyed by question_id
    derived_config  JSONB       NOT NULL DEFAULT '{}', -- what the LLM analysis produced
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
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

-- ── Shared World — Pokemon-style locations for group learning ───────────────

CREATE SCHEMA IF NOT EXISTS shared_world;

-- Who is at which location right now (one row per learner, TTL = 10 min idle)
CREATE TABLE IF NOT EXISTS shared_world.presence (
    learner_id   TEXT PRIMARY KEY,
    location_id  TEXT NOT NULL,
    learner_name TEXT DEFAULT '',
    emoji        TEXT DEFAULT '👤',
    color        TEXT DEFAULT '#64748b',
    last_seen    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS presence_location_idx
    ON shared_world.presence (location_id, last_seen DESC);

-- Shared message thread per location (all students see the same thread)
CREATE TABLE IF NOT EXISTS shared_world.messages (
    id          BIGSERIAL PRIMARY KEY,
    location_id TEXT NOT NULL,
    learner_id  TEXT NOT NULL,
    learner_name TEXT DEFAULT '',
    role        TEXT NOT NULL CHECK (role IN ('child','parth')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS world_messages_location_idx
    ON shared_world.messages (location_id, created_at DESC);

-- ── 15-Agent Harness: new tables ────────────────────────────────────────────

-- Emotion Compass: affect probability vector
CREATE TABLE IF NOT EXISTS learner_state.affect_state (
    learner_id  TEXT PRIMARY KEY,
    frustration REAL DEFAULT 0.1,
    confusion   REAL DEFAULT 0.15,
    boredom     REAL DEFAULT 0.1,
    curiosity   REAL DEFAULT 0.2,
    delight     REAL DEFAULT 0.1,
    uncertainty REAL DEFAULT 0.5,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Emotion Model v2: continuous (valence, intensity) state, additive alongside
-- the discrete probability vector above — same table, not a second one, per
-- Design Principle 2. `history` is a capped rolling window (see
-- emotion_engine.gear_shift's window) of recent [valence, intensity] points,
-- needed to read trajectory/slope rather than just the current point.
-- See modules/learner_state/EMOTION_MODEL_V2_DESIGN.md.
ALTER TABLE learner_state.affect_state ADD COLUMN IF NOT EXISTS valence   REAL DEFAULT 0.0;
ALTER TABLE learner_state.affect_state ADD COLUMN IF NOT EXISTS intensity REAL DEFAULT 0.2;
ALTER TABLE learner_state.affect_state ADD COLUMN IF NOT EXISTS affect_history JSONB DEFAULT '[]'::jsonb;
ALTER TABLE learner_state.affect_state ADD COLUMN IF NOT EXISTS affect_gear_shift TEXT DEFAULT 'hold_steady';

-- Curriculum Cartographer: seen concepts per learner
CREATE TABLE IF NOT EXISTS learner_state.curriculum_map (
    learner_id   TEXT NOT NULL,
    concept_id   TEXT NOT NULL,
    subject      TEXT DEFAULT '',
    grade        INT DEFAULT 6,
    first_seen   TIMESTAMPTZ DEFAULT now(),
    last_seen    TIMESTAMPTZ DEFAULT now(),
    seen_count   INT DEFAULT 1,
    PRIMARY KEY (learner_id, concept_id)
);

-- Challenge Calibrator: struggle streak and difficulty level
CREATE TABLE IF NOT EXISTS learner_state.challenge_state (
    learner_id            TEXT PRIMARY KEY,
    consecutive_struggles INT DEFAULT 0,
    frustration_threshold REAL DEFAULT 3.0,
    difficulty_level      REAL DEFAULT 0.5,
    updated_at            TIMESTAMPTZ DEFAULT now()
);

-- Transfer Weaver: analogy history (worked/failed per domain)
CREATE TABLE IF NOT EXISTS learner_state.analogy_history (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    domain      TEXT NOT NULL,
    worked      BOOLEAN DEFAULT true,
    concept_id  TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analogy_history_learner_idx
    ON learner_state.analogy_history (learner_id, created_at DESC);

-- Language Bridge: preferred language and code-mesh policy
CREATE TABLE IF NOT EXISTS learner_state.language_state (
    learner_id     TEXT PRIMARY KEY,
    preferred_lang TEXT DEFAULT 'english',
    language_ratio REAL DEFAULT 1.0,
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- Register Tuner: tone and sentence-length preference
CREATE TABLE IF NOT EXISTS learner_state.register_state (
    learner_id           TEXT PRIMARY KEY,
    sentence_length_pref TEXT DEFAULT 'medium',
    formality            REAL DEFAULT 0.5,
    updated_at           TIMESTAMPTZ DEFAULT now()
);

-- Humor & Delight Guide: humor tolerance and delight triggers
CREATE TABLE IF NOT EXISTS learner_state.delight_state (
    learner_id       TEXT PRIMARY KEY,
    humor_tolerance  REAL DEFAULT 0.5,
    delight_triggers TEXT DEFAULT '[]',
    nogo_zones       TEXT DEFAULT '["identity","religion","family","appearance"]',
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Inquiry Alchemist: SEL repair tracking
CREATE TABLE IF NOT EXISTS learner_state.inquiry_state (
    learner_id      TEXT PRIMARY KEY,
    repair_count    INT DEFAULT 0,
    last_repair_at  TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Family Alliance: caregiver context (consent-gated)
CREATE TABLE IF NOT EXISTS learner_state.family_context (
    learner_id      TEXT PRIMARY KEY,
    consent_level   INT DEFAULT 1,
    caregiver_lang  TEXT DEFAULT '',
    routines        TEXT DEFAULT '{}',
    home_supports   TEXT DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Rhythm & Time Steward: peak focus hour and pacing
CREATE TABLE IF NOT EXISTS learner_state.rhythm_state (
    learner_id            TEXT PRIMARY KEY,
    peak_hour             INT DEFAULT 15,
    session_count_today   INT DEFAULT 0,
    last_session_quality  REAL DEFAULT 5.0,
    updated_at            TIMESTAMPTZ DEFAULT now()
);

-- Pattern & Creation Guide: cross-scale pattern encounters
CREATE TABLE IF NOT EXISTS learner_state.pattern_state (
    learner_id             TEXT PRIMARY KEY,
    latest_pattern_message TEXT DEFAULT '',
    updated_at             TIMESTAMPTZ DEFAULT now()
);

-- SAINT+: knowledge tracing event log (elapsed_ms + lag_ms for temporal features)
CREATE TABLE IF NOT EXISTS learner_state.kt_events (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    concept_id  TEXT NOT NULL,
    correct     BOOLEAN NOT NULL,
    elapsed_ms  INT DEFAULT 0,
    lag_ms      INT DEFAULT 0,
    session_id  TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS kt_events_learner_idx
    ON learner_state.kt_events (learner_id, created_at DESC);

-- ── Agent 11: Confidence Calibration ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learner_state.confidence_calibration (
    learner_id     TEXT NOT NULL,
    concept_id     TEXT NOT NULL,
    stated_high    BOOLEAN DEFAULT false,
    actual_mastery REAL DEFAULT 0.0,
    gap            REAL DEFAULT 0.0,
    updated_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (learner_id, concept_id)
);

-- ── Learning Velocity: ZPD-normalized time-to-mastery estimate ───────────────
CREATE TABLE IF NOT EXISTS learner_state.learning_velocity_state (
    learner_id              TEXT PRIMARY KEY,
    velocity_score          REAL DEFAULT 0.5,
    confidence              REAL DEFAULT 0.0,
    zpd_distance            REAL DEFAULT 0.0,
    time_to_mastery_turns   REAL DEFAULT 0.0,
    sample_size             INT DEFAULT 0,
    evidence_json           JSONB DEFAULT '{}',
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- ── Motivation & Drive: voluntary returns after difficult turns ─────────────
CREATE TABLE IF NOT EXISTS learner_state.motivation_drive_state (
    learner_id               TEXT PRIMARY KEY,
    drive_score              REAL DEFAULT 0.5,
    confidence               REAL DEFAULT 0.0,
    return_after_difficulty  REAL,
    active_days_14           INT DEFAULT 0,
    avg_gap_hours            REAL,
    hard_return_count        INT DEFAULT 0,
    evidence_json            JSONB DEFAULT '{}',
    updated_at               TIMESTAMPTZ DEFAULT now()
);

-- ── Social Learning: group vs solo vs teach-back preference ─────────────────
CREATE TABLE IF NOT EXISTS learner_state.social_learning_state (
    learner_id              TEXT PRIMARY KEY,
    group_preference        REAL DEFAULT 0.5,
    solo_preference         REAL DEFAULT 0.5,
    teach_back_preference   REAL DEFAULT 0.5,
    sample_count            INT DEFAULT 0,
    last_signal             TEXT DEFAULT '',
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- ── Value & Purpose: periodic reflection, not per-message inference ─────────
CREATE TABLE IF NOT EXISTS learner_state.value_purpose_reflections (
    id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    learner_id     TEXT NOT NULL,
    prompt_id      TEXT NOT NULL,
    prompt_text    TEXT NOT NULL,
    response_text  TEXT NOT NULL,
    themes_json    JSONB DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS value_reflections_learner_idx
    ON learner_state.value_purpose_reflections (learner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS learner_state.value_purpose_state (
    learner_id      TEXT PRIMARY KEY,
    purpose_themes  JSONB DEFAULT '{}',
    values_json     JSONB DEFAULT '[]',
    confidence      REAL DEFAULT 0.0,
    sample_count    INT DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Product-facing 15-dimension snapshot cache ──────────────────────────────
CREATE TABLE IF NOT EXISTS learner_state.dimension_snapshots (
    learner_id     TEXT PRIMARY KEY,
    snapshot_json  JSONB NOT NULL DEFAULT '{}',
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- ── Developmental Lens Portraits ──────────────────────────────────────────────
-- Written by lens agents (cognitive, affect, psychological, contextual, relational).
-- One row per (learner, lens, run). Latest row per lens is the current portrait.
CREATE TABLE IF NOT EXISTS learner_state.lens_portraits (
    id           BIGSERIAL    PRIMARY KEY,
    learner_id   TEXT         NOT NULL,
    lens         TEXT         NOT NULL
                              CHECK (lens IN ('cognitive','affect','psychological','contextual','relational')),
    portrait     JSONB        NOT NULL DEFAULT '{}',
    narrative    TEXT         NOT NULL DEFAULT '',
    computed_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    period_start TIMESTAMPTZ,
    period_end   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS lens_portraits_learner_lens_idx
    ON learner_state.lens_portraits (learner_id, lens, computed_at DESC);

-- ── Pilot gate: pretest baseline snapshot ────────────────────────────────────
-- Recorded once, at or before the first session, so w4_gain can compare real
-- starting mastery rather than assuming a fixed prior.
CREATE TABLE IF NOT EXISTS metrics.learner_baselines (
    learner_id    TEXT PRIMARY KEY,
    avg_mastery   REAL NOT NULL DEFAULT 0.0,
    concept_count INT  NOT NULL DEFAULT 0,
    recorded_at   TIMESTAMPTZ DEFAULT now()
);

-- ── Pilot gate: guardian engagement log ──────────────────────────────────────
-- Written every time a guardian fetches the parent dashboard report.
-- Used by the guardian_engaged gate to prove the "sold to the parent" claim.
CREATE TABLE IF NOT EXISTS parent_dashboard.views (
    id          BIGSERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    viewed_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS parent_dashboard_views_learner_idx
    ON parent_dashboard.views (learner_id, viewed_at DESC);

-- ── Teacher portraits ────────────────────────────────────────────────────────
-- Teachers may not have the student's join code. Primary key is
-- (teacher_phone, student_name, subject) so a teacher can submit
-- portraits for multiple students without any app login or join code.
-- student_code and learner_id are optional — filled only when available.
CREATE SCHEMA IF NOT EXISTS teacher;

CREATE TABLE IF NOT EXISTS teacher.portraits (
    id              BIGSERIAL PRIMARY KEY,
    teacher_phone   TEXT NOT NULL,          -- teacher's mobile number (key)
    teacher_name    TEXT NOT NULL DEFAULT '',
    student_name    TEXT NOT NULL DEFAULT '',
    student_grade   TEXT,
    student_code    TEXT,                   -- optional 8-char join code
    learner_id      TEXT,                   -- resolved full UUID (nullable)
    subject         TEXT NOT NULL DEFAULT '',
    school          TEXT,
    payload         JSONB NOT NULL DEFAULT '{}',
    submitted_at    TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT teacher_portraits_uq UNIQUE (teacher_phone, student_name, subject)
);
CREATE INDEX IF NOT EXISTS teacher_portraits_learner_idx
    ON teacher.portraits (learner_id) WHERE learner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS teacher_portraits_phone_idx
    ON teacher.portraits (teacher_phone);

-- Add new columns to existing installations
-- Filled from a verified survey_links token at submission time (see below),
-- distinct from the free-text `school` field a teacher can type by hand.
ALTER TABLE teacher.portraits ADD COLUMN IF NOT EXISTS school_id TEXT;

-- ── Survey links — tokenized, trackable teacher-form invitations ────────────
-- Issued via POST /survey/link. `token` is a signed, expiring JWT; the row
-- exists so an open (GET /teacher/form?token=) and a submission can be
-- attributed back to a school/cohort without a full roster system.
CREATE TABLE IF NOT EXISTS teacher.survey_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       TEXT NOT NULL,
    teacher_phone   TEXT,
    token           TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    opened_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS teacher_survey_links_school_idx
    ON teacher.survey_links (school_id);

-- ── Notify — outbound comms log (email / sms / whatsapp) ────────────────────
-- Every send attempt via POST /notify/send is logged here, success or
-- failure, so a pilot lead can see why a reminder didn't land.
CREATE SCHEMA IF NOT EXISTS notify;

CREATE TABLE IF NOT EXISTS notify.log (
    id          BIGSERIAL PRIMARY KEY,
    recipient   TEXT NOT NULL,
    channel     TEXT NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
    template    TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('sent','failed')),
    error       TEXT,
    sent_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notify_log_recipient_idx
    ON notify.log (recipient, sent_at DESC);
