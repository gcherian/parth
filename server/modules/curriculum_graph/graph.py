"""
curriculum.graph — concept neighbourhood retrieval.

Combines two sources:
  1. Postgres concept_edges graph (structural prerequisites/co-reqs)
  2. ChromaDB vector search (semantic NCERT chunk retrieval)

Returns a merged curriculum_context string for tutor.runtime.
"""
import asyncio
from pathlib import Path

from foundation.observability import get_logger

log = get_logger("curriculum.graph")

# ChromaDB client is module-level singleton (safe: read-only after ingest)
_chroma_collection = None


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
            model_name="nomic-embed-text",
        )
        _chroma_collection = client.get_or_create_collection(
            "ncert",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_collection


async def retrieve_semantic(query: str, subject: str, grade: int, n_results: int = 3) -> str:
    """Vector search over NCERT chunks — runs in thread pool to avoid blocking."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _retrieve_sync, query, subject, grade, n_results)


def _retrieve_sync(query: str, subject: str, grade: int, n_results: int) -> str:
    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            return ""

        where = {}
        if subject and subject.lower() != "general":
            where["subject"] = {"$eq": subject.lower()}

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            where=where if where else None,
            include=["documents"],
        )
        docs = results.get("documents", [[]])[0]
        if not docs:
            return ""
        return "\n\n---\n\n".join(docs[:n_results])
    except Exception as e:
        log.warning("chroma_query_failed", error=str(e))
        return ""


async def get_concept_neighbourhood(conn, concept_ids: list[str]) -> list[dict]:
    """Return prerequisite + co-requisite concepts from the graph."""
    if not concept_ids or conn is None:
        return []
    try:
        rows = await conn.fetch(
            """
            SELECT c.id, c.label, ce.type
            FROM curriculum_graph.concept_edges ce
            JOIN curriculum_graph.concepts c ON c.id = ce.to_id
            WHERE ce.from_id = ANY($1)
            ORDER BY ce.type, c.label
            LIMIT 10
            """,
            concept_ids,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("graph_query_failed", error=str(e))
        return []
