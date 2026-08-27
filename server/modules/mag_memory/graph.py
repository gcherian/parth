"""
mag.memory — multi-graph episodic memory (semantic, temporal, causal, entity).

Complements curriculum_graph's RAG (static NCERT chunk retrieval) with a
dynamic, per-learner memory of the interaction history itself, modeled on
MAGMA (Jiang et al., ACL 2026): each turn becomes an event node; four
orthogonal edge types connect nodes; retrieval is a query-intent-aware
traversal rather than a flat similarity search.

This module holds the parts that are pure functions (classify_intent,
rrf_fuse, score_edge, linearize) alongside the Postgres/Chroma IO
(_get_collection, anchors, traverse) — same split as
modules/curriculum_graph/graph.py. Pure functions are exercised directly
in tests/test_mag_memory.py without a live DB or Chroma instance.
"""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone

from foundation.observability import get_logger

log = get_logger("mag.memory")

EMBED_MODEL = "bge-m3"   # must match ingest/build_index.py and curriculum_graph/graph.py —
                          # embeddings from different models sit in incompatible vector spaces
COLLECTION_NAME = "mag_events"

# ── Chroma collection (separate from curriculum_graph's "ncert" collection) ──

_chroma_collection = None

# curriculum_graph's "ncert" collection is read-only after an offline batch
# ingest, so concurrent reads from multiple executor threads are safe. This
# module's "mag_events" collection is written to live, on every turn — and
# chromadb's SQLite-backed PersistentClient does not document being safe for
# concurrent access from multiple threads in one process. Route every Chroma
# call (read or write) through this lock rather than assume thread safety
# the library doesn't promise; a hung/corrupted background consolidation
# task was observed in practice before this was added.
_chroma_lock = asyncio.Lock()


async def run_chroma(fn):
    async with _chroma_lock:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)


def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        import chromadb
        from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
        from config import Config

        chroma_path = Config.DATA_DIR / "chroma"
        client = chromadb.PersistentClient(path=str(chroma_path))
        embed_fn = OllamaEmbeddingFunction(
            url=f"{Config.OLLAMA_URL}/api/embeddings",
            model_name=EMBED_MODEL,
        )
        _chroma_collection = client.get_or_create_collection(
            COLLECTION_NAME,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_collection


# ── Query intent → edge-type bias ────────────────────────────────────────────
# The paper's φ(edge_type, intent): a learned weight vector per intent. We use
# a small fixed table instead of a learned classifier — Parth's existing
# heuristics (episodes.py, learner_state/signals.py) are all regex-based, so
# this keeps MAG consistent with the rest of the codebase rather than adding
# an ML dependency for a four-way classification.
INTENT_CAUSAL = "causal"
INTENT_TEMPORAL = "temporal"
INTENT_ENTITY = "entity"
INTENT_GENERAL = "general"

_EDGE_WEIGHTS: dict[str, dict[str, float]] = {
    INTENT_CAUSAL:   {"causal": 1.0, "temporal": 0.3, "entity": 0.3, "semantic": 0.5},
    INTENT_TEMPORAL: {"causal": 0.2, "temporal": 1.0, "entity": 0.2, "semantic": 0.4},
    INTENT_ENTITY:   {"causal": 0.3, "temporal": 0.2, "entity": 1.0, "semantic": 0.5},
    INTENT_GENERAL:  {"causal": 0.4, "temporal": 0.4, "entity": 0.4, "semantic": 0.6},
}

_WHY_RE = re.compile(
    r"\b(why|how\s+come|what\s+made|what\s+caused|kyun|kyunki)\b", re.IGNORECASE
)
_WHEN_RE = re.compile(
    r"\b(when|last\s+time|yesterday|before|earlier|previously|remember\s+when|"
    r"used\s+to|ago|pehle|kab)\b", re.IGNORECASE
)
_ENTITY_RE = re.compile(
    r"\b(what\s+did\s+i\s+(say|ask)|what\s+about|remind\s+me|which\s+one|"
    r"the\s+one\s+(about|where))\b", re.IGNORECASE
)


def classify_intent(message: str) -> str:
    """Map a query to one of causal / temporal / entity / general.

    Order matters: a "why...last time" message is treated as causal — cause
    dominates recency when both are present, since it's the harder signal to
    recover once lost (mirrors the paper's finding that causal edges are the
    single highest-impact ablation).
    """
    if _WHY_RE.search(message):
        return INTENT_CAUSAL
    if _ENTITY_RE.search(message):
        return INTENT_ENTITY
    if _WHEN_RE.search(message):
        return INTENT_TEMPORAL
    return INTENT_GENERAL


def edge_weight(edge_type: str, intent: str) -> float:
    return _EDGE_WEIGHTS.get(intent, _EDGE_WEIGHTS[INTENT_GENERAL]).get(edge_type, 0.3)


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Fuse several ranked id lists into one score per id (Cormack et al., 2009).

    Robust to a signal being empty or missing an id entirely — that id
    simply gets no contribution from that ranking, not a penalty.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] += 1.0 / (k + rank + 1)
    return dict(scores)


# ── Traversal scoring ─────────────────────────────────────────────────────────

DECAY = 0.7   # per-hop score decay — keeps the beam from wandering far from the anchor


def score_transition(edge_type: str, edge_weight_value: float, intent: str, hop: int) -> float:
    """S(n_j | n_i, q) from the paper, simplified: structural alignment
    (edge type vs. query intent) times the edge's own stored weight
    (cosine similarity for semantic edges, LLM confidence for causal edges),
    decayed per hop so the beam favours nearby, well-aligned evidence over
    a long walk of weakly-relevant hops."""
    return edge_weight(edge_type, intent) * edge_weight_value * (DECAY ** hop)


async def traverse(
    conn, learner_id: str, anchor_ids: list[str], intent: str,
    max_hops: int = 2, beam_width: int = 6, budget: int = 6,
) -> list[dict]:
    """Heuristic beam search over mag_memory.edges starting from anchor_ids.

    Visits nodes up to max_hops away, keeping only the top beam_width
    candidates at each hop (Algorithm 1 in the paper, without the semantic
    re-scoring term — see score_transition's docstring for why). Returns up
    to `budget` node rows, richest-first.
    """
    if not anchor_ids:
        return []

    visited: dict[str, dict] = {}
    frontier = list(anchor_ids)
    for node_id in frontier:
        visited[node_id] = {"id": node_id, "score": 1.0, "hop": 0}

    for hop in range(1, max_hops + 1):
        if not frontier:
            break
        rows = await conn.fetch(
            """
            SELECT src_id::text AS src_id, dst_id::text AS dst_id,
                   edge_type, weight
            FROM mag_memory.edges
            WHERE src_id = ANY($1::uuid[]) OR dst_id = ANY($1::uuid[])
            """,
            frontier,
        )
        candidates: dict[str, float] = defaultdict(float)
        for row in rows:
            for this_end, other_end in ((row["src_id"], row["dst_id"]), (row["dst_id"], row["src_id"])):
                if this_end not in frontier or other_end in visited:
                    continue
                s = score_transition(row["edge_type"], row["weight"], intent, hop)
                candidates[other_end] = max(candidates[other_end], s)

        top = sorted(candidates.items(), key=lambda kv: kv[1], reverse=True)[:beam_width]
        frontier = [node_id for node_id, _ in top]
        for node_id, s in top:
            visited[node_id] = {"id": node_id, "score": s, "hop": hop}

    if not visited:
        return []

    node_rows = await conn.fetch(
        """
        SELECT id::text AS id, learner_id, content, concept_ids, ts
        FROM mag_memory.nodes
        WHERE id = ANY($1::uuid[]) AND learner_id = $2
        """,
        list(visited.keys()), learner_id,
    )
    enriched = []
    for row in node_rows:
        d = dict(row)
        d["score"] = visited[d["id"]]["score"]
        enriched.append(d)

    enriched.sort(key=lambda d: d["score"], reverse=True)
    return enriched[:budget]


# ── Context synthesis (Stage 4: narrative linearization) ────────────────────

def _age_label(ts) -> str:
    now = datetime.now(timezone.utc)
    dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    days = (now - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        return f"{days // 7} week(s) ago"
    return f"{days // 30} month(s) ago"


def linearize(nodes: list[dict], intent: str) -> str:
    """Turn a retrieved subgraph into a structured, provenance-tagged prompt
    block (Stage 4 of the paper — topological ordering + context scaffolding).

    Ordering: chronological. For this scoped implementation temporal order
    doubles as the causal chain order too, since every causal edge in this
    system is constructed pointing from an earlier node to a later one
    (see consolidate.py) — a true topological sort and a ts-sort agree here.
    """
    if not nodes:
        return ""

    ordered = sorted(nodes, key=lambda d: d["ts"])
    lines = ["What I remember from this learner's own history (not the textbook):"]
    for n in ordered:
        age = _age_label(n["ts"])
        short_id = str(n["id"])[:8]
        lines.append(f"  • [{age}, ref:{short_id}] {n['content']}")
    lines.append(
        "Reference these naturally when relevant to the current question — "
        "don't just list them back."
    )
    return "\n".join(lines)
