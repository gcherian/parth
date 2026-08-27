"""
mag.memory — query-time retrieval (Stages 1-4 of the paper's Adaptive
Hierarchical Retrieval): classify intent, fuse multi-signal anchors,
traverse the graph, linearize into a prompt block.

Entry point: build_memory_context(conn, learner_id, message).
"""
from __future__ import annotations

from config import Config
from foundation.observability import get_logger
from modules.mag_memory.graph import (
    classify_intent,
    rrf_fuse,
    traverse,
    linearize,
    _get_collection,
    run_chroma,
)

log = get_logger("mag.memory.retrieval")

_RECENCY_POOL = 30   # candidate pool size for the recency + keyword signals
_ANCHOR_K = 5        # anchors handed to the graph traversal


def _keyword_overlap_ranking(message: str, pool: list[dict]) -> list[str]:
    """Rank a candidate pool by word overlap with the query — the cheap
    lexical-match signal in the paper's anchor fusion (RRF stage), computed
    over the same recency pool rather than a separate inverted index."""
    query_words = set(message.lower().split())
    if not query_words:
        return []
    scored = []
    for row in pool:
        content_words = set(row["content"].lower().split())
        overlap = len(query_words & content_words)
        if overlap > 0:
            scored.append((row["id"], overlap))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return [node_id for node_id, _ in scored]


async def _vector_ranking(learner_id: str, message: str, n: int) -> list[str]:
    def _query():
        collection = _get_collection()
        if collection.count() == 0:
            return []
        results = collection.query(
            query_texts=[message],
            n_results=min(n, collection.count()),
            where={"learner_id": learner_id},
            include=[],
        )
        return results.get("ids", [[]])[0]

    try:
        return await run_chroma(_query)
    except Exception as e:
        log.warning("mag_vector_ranking_failed", error=str(e))
        return []


async def get_anchors(conn, learner_id: str, message: str) -> tuple[list[str], list[dict]]:
    """Stage 2: Multi-Signal Anchor Identification. Returns (anchor_ids, recency_pool)
    — the pool is reused by build_memory_context to avoid a second DB round-trip."""
    pool_rows = await conn.fetch(
        """
        SELECT id::text AS id, content, ts
        FROM mag_memory.nodes
        WHERE learner_id = $1
        ORDER BY ts DESC
        LIMIT $2
        """,
        learner_id, _RECENCY_POOL,
    )
    pool = [dict(r) for r in pool_rows]
    if not pool:
        return [], []

    recency_ranking = [r["id"] for r in pool]
    keyword_ranking = _keyword_overlap_ranking(message, pool)
    vector_ranking = await _vector_ranking(learner_id, message, n=8)

    fused = rrf_fuse([vector_ranking, recency_ranking, keyword_ranking])
    anchors = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:_ANCHOR_K]
    return [node_id for node_id, _ in anchors], pool


async def build_memory_context(conn, learner_id: str, message: str) -> str:
    """Full query pipeline. Never raises — a memory-retrieval failure should
    degrade to no memory context, not break the turn."""
    if not Config.MAG_ENABLED:
        return ""
    try:
        intent = classify_intent(message)
        anchors, _pool = await get_anchors(conn, learner_id, message)
        if not anchors:
            return ""
        subgraph = await traverse(
            conn, learner_id, anchors, intent,
            max_hops=Config.MAG_MAX_HOPS, budget=Config.MAG_CONTEXT_BUDGET,
        )
        return linearize(subgraph, intent)
    except Exception as e:
        log.warning("mag_memory_context_failed", error=str(e))
        return ""
