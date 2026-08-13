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


EMBED_MODEL = "bge-m3"   # materially better Hindi/Hinglish retrieval than
                          # nomic-embed-text — matters given Parth's code-
                          # switching design. Must match ingest/build_index.py's
                          # EMBED_MODEL exactly, or ingestion and retrieval sit
                          # in different, incompatible vector spaces.
BOARD = "cbse"            # matches ingest/build_index.py's BOARD; the only
                          # board with content ingested this pass


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
            "ncert",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_collection


async def retrieve_semantic(
    query: str,
    subject: str,
    grade: int,
    n_results: int = 3,
    weak_concepts: list[str] | None = None,
    misconception_hint: str = "",
) -> str:
    """Vector search over NCERT chunks — runs in thread pool to avoid blocking.

    weak_concepts/misconception_hint bias retrieval by augmenting the query
    text before embedding (a "boost" implemented as query augmentation, not
    post-hoc re-ranking — the existing design already does one embedding
    call per query, and individual chunks don't reliably carry a concept_id
    to re-rank against)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _retrieve_sync, query, subject, grade, n_results, weak_concepts, misconception_hint
    )


def _build_where_tiers(subject_norm: str | None, grade: int | None) -> list[dict | None]:
    """Most-specific to least-specific filter tiers. A facet is omitted
    (not stacked as an always-true clause) when it isn't available, so a
    "general" subject with a real grade still gets a grade+board tier
    instead of silently skipping straight to unfiltered."""
    def combine(*clauses: dict | None) -> dict | None:
        present = [c for c in clauses if c]
        if not present:
            return None
        return present[0] if len(present) == 1 else {"$and": present}

    subject_clause = {"subject": {"$eq": subject_norm}} if subject_norm else None
    grade_clause = {"grade": {"$lte": grade + 1}} if grade is not None else None
    board_clause = {"board": {"$eq": BOARD}}

    tiers = [
        combine(subject_clause, grade_clause, board_clause),
        combine(subject_clause, board_clause),
        None,  # unfiltered
    ]
    # De-dup adjacent tiers that collapse to the same clause (e.g. no
    # subject given, so tier 1 and tier 2 are identical).
    deduped: list[dict | None] = []
    for t in tiers:
        if not deduped or t != deduped[-1]:
            deduped.append(t)
    return deduped


def _retrieve_sync(
    query: str, subject: str, grade: int, n_results: int,
    weak_concepts: list[str] | None = None, misconception_hint: str = "",
) -> str:
    from config import Config

    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            return ""

        query_text = query
        if weak_concepts:
            query_text = f"{query_text}. Related to: {weak_concepts[0]}"
        if misconception_hint:
            query_text = f"{query_text}. Common misconception: {misconception_hint}"

        subject_norm = subject.lower() if subject and subject.lower() != "general" else None
        n = min(n_results, count)

        results = None
        docs: list[str] = []
        for where in _build_where_tiers(subject_norm, grade):
            results = collection.query(
                query_texts=[query_text],
                n_results=n,
                where=where,
                include=["documents", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            if len(docs) >= 2:
                break

        if not docs:
            return ""

        distances = results.get("distances", [[]])[0]
        good = [
            doc for doc, dist in zip(docs, distances)
            if (1 - dist) > Config.RAG_SCORE_THRESHOLD
        ]
        if not good:
            return ""
        return "\n\n---\n\n".join(good[:n_results])
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
