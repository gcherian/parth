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


async def get_next_concept(
    conn, learner_id: str, grade: int, subject: str | None = None
) -> dict | None:
    """
    Return the most appropriate next concept for a learner based on the
    curriculum prerequisite graph and current mastery levels.

    Selection criteria:
    - All prerequisites are sufficiently mastered (p_mastery > 0.45) or concept has none
    - Concept is not yet mastered (p_mastery < 0.70)
    - Grade-appropriate (allows one grade below for remediation)

    Priority: exposed-but-unmastered > grade-appropriate > subject-filtered
    Returns: dict with concept_id, label, reason, p_mastery — or None.
    """
    if conn is None:
        return None
    try:
        row = await conn.fetchrow(
            """
            SELECT c.id, c.label, c.subject, c.grade_min,
                   COALESCE(k.p_mastery, 0.0) AS p_mastery,
                   COALESCE(k.exposures, 0)   AS exposures
            FROM curriculum_graph.concepts c
            LEFT JOIN learner_state.knowledge k
                ON k.concept_id = c.id AND k.learner_id = $1
            WHERE
                -- All prerequisites met (mastery > 0.45) or concept has no prerequisites
                NOT EXISTS (
                    SELECT 1 FROM curriculum_graph.concept_edges e
                    LEFT JOIN learner_state.knowledge k2
                        ON k2.concept_id = e.from_id AND k2.learner_id = $1
                    WHERE e.to_id = c.id
                      AND e.type = 'prerequisite'
                      AND COALESCE(k2.p_mastery, 0) < 0.45
                )
                -- Not yet mastered
                AND COALESCE(k.p_mastery, 0) < 0.70
                -- Grade appropriate (allow one grade below for remediation)
                AND c.grade_min <= $2
                AND c.grade_max >= $2 - 1
            ORDER BY
                COALESCE(k.exposures, 0) DESC,   -- exposed-but-unmastered first
                COALESCE(k.p_mastery,  0) DESC,   -- highest partial mastery next
                c.grade_min               DESC    -- most advanced fitting grade last
            LIMIT 1
            """,
            learner_id,
            grade,
        )
        if row is None:
            return None

        p_mastery = float(row["p_mastery"])
        exposures = int(row["exposures"])

        if exposures > 0:
            reason = f"You have seen this before (mastery {p_mastery:.0%}) — let's strengthen it."
        else:
            reason = "Prerequisites are mastered — this is the natural next step."

        # Apply subject filter as a preference (not a hard filter) — if result
        # doesn't match requested subject, note it but still return
        result = {
            "concept_id": row["id"],
            "label":      row["label"],
            "reason":     reason,
            "p_mastery":  p_mastery,
        }

        # If caller specified a subject and this concept is different, try to find
        # a same-subject match first (best-effort retry with subject constraint)
        if subject and row["subject"] != subject.lower():
            subject_row = await conn.fetchrow(
                """
                SELECT c.id, c.label, c.subject, c.grade_min,
                       COALESCE(k.p_mastery, 0.0) AS p_mastery,
                       COALESCE(k.exposures, 0)   AS exposures
                FROM curriculum_graph.concepts c
                LEFT JOIN learner_state.knowledge k
                    ON k.concept_id = c.id AND k.learner_id = $1
                WHERE
                    NOT EXISTS (
                        SELECT 1 FROM curriculum_graph.concept_edges e
                        LEFT JOIN learner_state.knowledge k2
                            ON k2.concept_id = e.from_id AND k2.learner_id = $1
                        WHERE e.to_id = c.id
                          AND e.type = 'prerequisite'
                          AND COALESCE(k2.p_mastery, 0) < 0.45
                    )
                    AND COALESCE(k.p_mastery, 0) < 0.70
                    AND c.grade_min <= $2
                    AND c.grade_max >= $2 - 1
                    AND c.subject = $3
                ORDER BY
                    COALESCE(k.exposures, 0) DESC,
                    COALESCE(k.p_mastery,  0) DESC,
                    c.grade_min               DESC
                LIMIT 1
                """,
                learner_id,
                grade,
                subject.lower(),
            )
            if subject_row is not None:
                p2 = float(subject_row["p_mastery"])
                exp2 = int(subject_row["exposures"])
                reason2 = (
                    f"You have seen this before (mastery {p2:.0%}) — let's strengthen it."
                    if exp2 > 0
                    else "Prerequisites are mastered — this is the natural next step."
                )
                result = {
                    "concept_id": subject_row["id"],
                    "label":      subject_row["label"],
                    "reason":     reason2,
                    "p_mastery":  p2,
                }

        log.debug("get_next_concept", learner_id=learner_id, grade=grade, result=result)
        return result

    except Exception as e:
        log.warning("get_next_concept_failed", error=str(e))
        return None


async def get_remediation(conn, concept_id: str, misconception_text: str) -> dict | None:
    """
    Find the best-matching remediation for a learner's misconception.

    Performs keyword matching: splits misconception_pattern into words and
    counts how many appear in misconception_text. Returns the row with the
    highest overlap, or None if the table is empty / no match found.
    """
    if conn is None or not concept_id or not misconception_text:
        return None
    try:
        rows = await conn.fetch(
            """
            SELECT id, concept_id, misconception_pattern,
                   remediation_text, worked_example, analogy_hint
            FROM curriculum_graph.misconception_remediations
            WHERE concept_id = $1
            """,
            concept_id,
        )
        if not rows:
            return None

        needle = misconception_text.lower()
        best_row = None
        best_score = -1

        for row in rows:
            pattern_words = row["misconception_pattern"].lower().split()
            score = sum(1 for w in pattern_words if w in needle)
            if score > best_score:
                best_score = score
                best_row = row

        if best_row is None or best_score == 0:
            # Fall back to the first row for the concept if no keyword matched
            best_row = rows[0]

        return {
            "remediation_text": best_row["remediation_text"],
            "worked_example":   best_row["worked_example"],
            "analogy_hint":     best_row["analogy_hint"],
        }

    except Exception as e:
        log.warning("get_remediation_failed", error=str(e))
        return None
