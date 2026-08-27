"""
mag.memory — Slow Path: Structural Consolidation (Algorithm 3 in the paper).

Runs as a fire-and-forget background task after the fast path (ingest.py)
has already returned the turn to the child — nothing here can add latency
to a request. Opens its own DB connection (the request's connection is
gone by the time this runs), inspects the new node's local neighborhood,
and densifies the graph with the three edge types the fast path doesn't
create: semantic (embedding similarity, already computed by Chroma),
entity (shared concept references — set overlap, no LLM needed), and
causal (an LLM call — the one place in MAG that reasons about *why*).
"""
from __future__ import annotations

import json
import re

import httpx

from config import Config
from foundation.observability import get_logger
from modules.mag_memory.graph import _get_collection, run_chroma

log = get_logger("mag.memory.consolidate")

_TEMPORAL_WINDOW = 5     # prior events considered as causal candidates
_SEMANTIC_K = 5          # nearest neighbours pulled from Chroma

_CAUSAL_PROMPT = """\
You are analyzing a student's tutoring history to find cause-and-effect links.

Earlier moments with this student (oldest first):
{candidates}

Latest moment:
{latest}

Which earlier moments (by number) plausibly led to or explain the latest one?
Only include a moment if there's a real causal link, not just topic similarity —
e.g. a stated misconception causing a later struggle, or a breakthrough
enabling a later connection. Respond with ONLY a JSON object, no explanation:
{{"causal_from": [<numbers>], "rationale": "one short sentence, or empty if none"}}"""


async def consolidate_node(
    pool, node_id: str, learner_id: str, content: str, concept_ids: list[str],
) -> None:
    """Precondition: node_id already exists in mag_memory.nodes and is queued
    in mag_memory.consolidation_queue. content/concept_ids are the same
    values the fast path (ingest.py) just wrote for this node — passed in
    directly rather than re-read here, because this background task opens
    its own connection, and the request's own transaction that inserted
    node_id may not have committed yet (asyncio can schedule this task
    before ctx.db's transaction closes). A fresh SELECT on a separate
    connection would race that commit under READ COMMITTED and silently see
    nothing — this was observed in practice, 100% reproducibly, before the
    fix. The edge INSERTs below still reference node_id as a foreign key, so
    Postgres itself may make them briefly wait on that same commit — that's
    fine, it's a bounded wait, not a race with a silent-failure mode.
    Postcondition: zero or more semantic/entity/causal edges point into
    node_id, and its queue row is marked processed — exactly once, even if
    this races another run for the same node (every write here is ON
    CONFLICT DO NOTHING). Never raises: this is a background task with no
    caller to report a failure to."""
    try:
        async with pool.acquire() as conn:
            await _add_entity_edges(conn, node_id, learner_id, concept_ids)
            await _add_semantic_edges(conn, node_id, learner_id, content)
            await _add_causal_edges(conn, node_id, learner_id, content)

            await conn.execute(
                "UPDATE mag_memory.consolidation_queue SET processed_at = now() "
                "WHERE node_id = $1::uuid",
                node_id,
            )
            log.debug("mag_node_consolidated", learner_id=learner_id, node_id=node_id)
    except Exception as e:
        log.warning("mag_consolidation_failed", node_id=node_id, error=str(e))


async def _add_entity_edges(conn, node_id: str, learner_id: str, concept_ids: list[str]) -> None:
    if not concept_ids:
        return
    rows = await conn.fetch(
        """
        SELECT id::text AS id FROM mag_memory.nodes
        WHERE learner_id = $1 AND id != $2::uuid AND concept_ids && $3
        ORDER BY ts DESC LIMIT $4
        """,
        learner_id, node_id, concept_ids, _TEMPORAL_WINDOW,
    )
    for row in rows:
        await conn.execute(
            """
            INSERT INTO mag_memory.edges (src_id, dst_id, edge_type, weight)
            VALUES ($1::uuid, $2::uuid, 'entity', 1.0)
            ON CONFLICT (src_id, dst_id, edge_type) DO NOTHING
            """,
            row["id"], node_id,
        )


async def _add_semantic_edges(conn, node_id: str, learner_id: str, content: str) -> None:
    def _query():
        collection = _get_collection()
        if collection.count() < 2:
            return [], []
        results = collection.query(
            query_texts=[content],
            n_results=min(_SEMANTIC_K + 1, collection.count()),
            where={"learner_id": learner_id},
            include=["distances"],
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return ids, distances

    try:
        ids, distances = await run_chroma(_query)
    except Exception as e:
        log.warning("mag_semantic_query_failed", error=str(e))
        return

    for neighbor_id, dist in zip(ids, distances):
        if neighbor_id == node_id:
            continue
        similarity = 1 - dist
        if similarity <= Config.MAG_SEMANTIC_THRESHOLD:
            continue
        await conn.execute(
            """
            INSERT INTO mag_memory.edges (src_id, dst_id, edge_type, weight)
            VALUES ($1::uuid, $2::uuid, 'semantic', $3)
            ON CONFLICT (src_id, dst_id, edge_type) DO UPDATE SET weight = EXCLUDED.weight
            """,
            neighbor_id, node_id, float(similarity),
        )


async def _add_causal_edges(conn, node_id: str, learner_id: str, latest_content: str) -> None:
    candidates = await conn.fetch(
        """
        SELECT id::text AS id, content FROM mag_memory.nodes
        WHERE learner_id = $1 AND id != $2::uuid
        ORDER BY ts DESC LIMIT $3
        """,
        learner_id, node_id, _TEMPORAL_WINDOW,
    )
    if not candidates:
        return
    candidates = list(reversed(candidates))  # oldest first, matches the prompt's framing

    numbered = "\n".join(f"{i+1}. {row['content']}" for i, row in enumerate(candidates))
    prompt = _CAUSAL_PROMPT.format(candidates=numbered, latest=latest_content)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={
                    "model": Config.FAST_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            r.raise_for_status()
        raw = r.json().get("response", "")
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return
        data = json.loads(match.group())
        rationale = str(data.get("rationale", ""))[:300]
        for idx in data.get("causal_from", []):
            i = int(idx) - 1
            if 0 <= i < len(candidates):
                await conn.execute(
                    """
                    INSERT INTO mag_memory.edges (src_id, dst_id, edge_type, weight, rationale)
                    VALUES ($1::uuid, $2::uuid, 'causal', 0.85, $3)
                    ON CONFLICT (src_id, dst_id, edge_type) DO NOTHING
                    """,
                    candidates[i]["id"], node_id, rationale,
                )
    except Exception as e:
        log.warning("mag_causal_inference_failed", error=str(e))
