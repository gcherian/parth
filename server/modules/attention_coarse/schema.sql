-- ── attention_coarse — server-side receiving contract for Invariant 03 ─────
-- Business plan §9: "Never use the camera for monitoring. Commitment: Focus
-- and fatigue inferred on-device from conversation only. Enforcement:
-- Federated attention layer — raw signals never leave the phone; only
-- coarse state is transmitted."
--
-- The on-device inference is a mobile-client capability (out of scope here).
-- This schema stores ONLY the coarse enum state the client sends — see
-- modules/attention_coarse/routes.py for the payload-shape rejection that
-- keeps raw signal (frames, images, embeddings, base64 blobs) from ever
-- reaching this table.

CREATE SCHEMA IF NOT EXISTS attention_coarse;

CREATE TABLE IF NOT EXISTS attention_coarse.states (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL,
    session_id  TEXT NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('focused', 'distracted', 'fatigued')),
    ts          TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per (child, session, ts) — a resend of the same coarse-state
-- reading is a no-op rather than a duplicate row.
CREATE UNIQUE INDEX IF NOT EXISTS attention_coarse_states_dedup_idx
    ON attention_coarse.states (child_id, session_id, ts);

CREATE INDEX IF NOT EXISTS attention_coarse_states_child_idx
    ON attention_coarse.states (child_id, ts DESC);
