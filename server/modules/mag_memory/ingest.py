"""
mag.memory — Fast Path: Synaptic Ingestion (Algorithm 2 in the paper).

Runs on the critical path (inside the same request that just got a tutor
response), so it does only non-blocking, cheap work: turn the completed
interaction into one event node, link it to the learner's previous node
with a temporal edge, embed it, and enqueue it for the slow path
(consolidate.py) to reason about causal/entity/semantic links later.
No LLM call happens here — that's the whole point of the two-speed design.
"""
from __future__ import annotations

from foundation.observability import get_logger
from modules.mag_memory.graph import _get_collection, run_chroma

log = get_logger("mag.memory.ingest")

_MAX_CONTENT_CHARS = 600


def _build_content(message: str, response_text: str) -> str:
    q = message.strip()[:300]
    a = response_text.strip()[:300]
    return f"Asked: {q}\nParth explained: {a}"[:_MAX_CONTENT_CHARS]


async def ingest_turn(
    conn, learner_id: str, request_id: str,
    message: str, response_text: str, concept_ids: list[str],
) -> tuple[str | None, str]:
    """Precondition: called once per completed interaction, with the same
    request_id the kernel used for this turn (the idempotency key — a retry
    of the same request must not create a second node). Postcondition: one
    row exists in mag_memory.nodes for (learner_id, request_id); if it is a
    new row, it has a temporal edge from the learner's previous node and is
    queued for slow-path consolidation. Returns (node_id, content); node_id
    is None if the Postgres write itself failed (never raises — a memory-
    write failure must not affect the child's turn, which has already
    completed). Embedding is deliberately NOT done here — see embed_node —
    so a slow/cold Ollama embedding call can never add latency to this
    request or make an otherwise-successful write look like a failure."""
    content = _build_content(message, response_text)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO mag_memory.nodes (learner_id, request_id, content, concept_ids)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (learner_id, request_id) WHERE request_id IS NOT NULL DO NOTHING
            RETURNING id::text AS id
            """,
            learner_id, request_id, content, concept_ids,
        )
        if row is None:
            # Either a genuine retry (already ingested) or a race — either way,
            # nothing new to link/enqueue.
            existing = await conn.fetchval(
                "SELECT id::text FROM mag_memory.nodes WHERE learner_id=$1 AND request_id=$2",
                learner_id, request_id,
            )
            return existing, content
        node_id = row["id"]

        prev_id = await conn.fetchval(
            """
            SELECT id::text FROM mag_memory.nodes
            WHERE learner_id = $1 AND id != $2::uuid
            ORDER BY ts DESC LIMIT 1
            """,
            learner_id, node_id,
        )
        if prev_id:
            await conn.execute(
                """
                INSERT INTO mag_memory.edges (src_id, dst_id, edge_type, weight)
                VALUES ($1::uuid, $2::uuid, 'temporal', 1.0)
                ON CONFLICT (src_id, dst_id, edge_type) DO NOTHING
                """,
                prev_id, node_id,
            )

        await conn.execute(
            "INSERT INTO mag_memory.consolidation_queue (node_id) VALUES ($1::uuid) "
            "ON CONFLICT (node_id) DO NOTHING",
            node_id,
        )

        log.info("mag_node_ingested", learner_id=learner_id, node_id=node_id, linked=bool(prev_id))
        return node_id, content
    except Exception as e:
        log.warning("mag_ingest_failed", learner_id=learner_id, error=str(e))
        return None, content


async def embed_node(node_id: str, learner_id: str, content: str) -> None:
    """Best-effort, meant to be fired via asyncio.create_task (never awaited
    on the request path — see module.py). A failure here just means this
    node won't surface via semantic anchor search or semantic edges until a
    later node's consolidation pass re-embeds around it; it does not affect
    the node's temporal/causal/entity standing, which are Postgres-only."""
    def _add():
        collection = _get_collection()
        collection.add(
            ids=[node_id],
            documents=[content],
            metadatas=[{"learner_id": learner_id}],
        )

    try:
        await run_chroma(_add)
        log.debug("mag_node_embedded", learner_id=learner_id, node_id=node_id)
    except Exception as e:
        log.warning("mag_embed_failed", learner_id=learner_id, node_id=node_id, error=str(e))
