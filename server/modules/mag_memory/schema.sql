-- ── MAG (Memory-Augmented Generation) — graph-based episodic memory ────────
-- Complements curriculum_graph's RAG (static NCERT retrieval) with a
-- per-learner, per-turn memory graph: every interaction becomes an event
-- node, connected to other events via up to four relation types —
-- temporal (chronological), causal (LLM-inferred "this led to that"),
-- entity (shared concept/domain reference), and semantic (embedding
-- similarity, materialised as edges once consolidation runs; the raw
-- vectors themselves live in Chroma's "mag_events" collection, not here).
--
-- Modeled on MAGMA (Jiang et al., ACL 2026, arXiv:2026.acl-long.1709):
-- a multi-graph agentic memory architecture with a fast synaptic-ingestion
-- path (this module's ingest.py) and a slow structural-consolidation path
-- (consolidate.py) that runs asynchronously after the response is sent.

CREATE SCHEMA IF NOT EXISTS mag_memory;

CREATE TABLE IF NOT EXISTS mag_memory.nodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learner_id  TEXT NOT NULL,
    request_id  UUID,                    -- idempotency key: one node per interaction
    content     TEXT NOT NULL,            -- "Asked: ...\nParth explained: ..."
    concept_ids TEXT[] DEFAULT '{}',      -- doubles as the entity-graph reference set
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS mag_nodes_learner_request_idx
    ON mag_memory.nodes (learner_id, request_id) WHERE request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS mag_nodes_learner_ts_idx
    ON mag_memory.nodes (learner_id, ts DESC);

CREATE TABLE IF NOT EXISTS mag_memory.edges (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_id     UUID NOT NULL REFERENCES mag_memory.nodes(id) ON DELETE CASCADE,
    dst_id     UUID NOT NULL REFERENCES mag_memory.nodes(id) ON DELETE CASCADE,
    edge_type  TEXT NOT NULL CHECK (edge_type IN ('temporal', 'causal', 'entity', 'semantic')),
    weight     REAL NOT NULL DEFAULT 1.0,   -- cosine sim (semantic), LLM confidence (causal), 1.0 otherwise
    rationale  TEXT DEFAULT '',             -- LLM's stated reason, for causal edges only
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (src_id, dst_id, edge_type)
);

CREATE INDEX IF NOT EXISTS mag_edges_src_idx ON mag_memory.edges (src_id, edge_type);
CREATE INDEX IF NOT EXISTS mag_edges_dst_idx ON mag_memory.edges (dst_id, edge_type);

-- Slow-path work queue: the fast path enqueues every new node here;
-- a background task dequeues, infers causal/entity/semantic edges, marks done.
CREATE TABLE IF NOT EXISTS mag_memory.consolidation_queue (
    node_id      UUID PRIMARY KEY REFERENCES mag_memory.nodes(id) ON DELETE CASCADE,
    enqueued_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
