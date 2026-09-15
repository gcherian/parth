-- ── Wonder Engine — cross-domain discovery detours during ordinary chat ────
-- Bridges the existing 300-puzzle discovery library (data/puzzles/v2/,
-- authored "discovered, not delivered") into the main tutoring loop.
-- Previously that library was only reachable via puzzle_engine's separate
-- cold-start onboarding window (puzzle_engine/cold_start.py's Bridge
-- puzzle, probe 4) — this schema tracks the same offer as a standing,
-- signal-gated capability across every session, not just the first five
-- interactions.

CREATE SCHEMA IF NOT EXISTS wonder_engine;

CREATE TABLE IF NOT EXISTS wonder_engine.offers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learner_id  TEXT NOT NULL,
    puzzle_id   TEXT NOT NULL,
    sphere      TEXT NOT NULL,
    offered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    engaged     BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS wonder_offers_learner_idx
    ON wonder_engine.offers (learner_id, offered_at DESC);
