"""Meaning graph retrieval, prompt context, and Neo4j export helpers."""
from __future__ import annotations

import json
import re
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "should", "that", "the", "their", "this", "to", "was",
    "we", "what", "when", "where", "who", "why", "with", "you", "your",
}


def age_for_grade(grade: int | str | None) -> int:
    """Approximate child age for the first-ten-years graph from school grade."""
    try:
        grade_i = int(grade or 3)
    except (TypeError, ValueError):
        grade_i = 3
    return max(5, min(10, grade_i + 5))


def clamp_age(age: int | str | None) -> int:
    try:
        age_i = int(age or 8)
    except (TypeError, ValueError):
        age_i = 8
    return max(5, min(10, age_i))


def normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip().lower()
    if not clean or clean in {"all", "any", "none"}:
        return None
    return clean


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall((text or "").lower()) if t not in _STOPWORDS}


def _candidate_text(candidate: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "title", "story_label", "story_summary", "setup", "suspense_question",
        "moral_tension", "nature_bridge", "deeper_question", "parent_hint",
        "parth_reasoning",
    ):
        value = candidate.get(key)
        if value:
            values.append(str(value))
    for key in ("concept_ids", "motif_ids", "story_tags"):
        values.extend(str(v) for v in candidate.get(key) or [])
    return " ".join(values)


def score_candidate(message: str, candidate: dict[str, Any]) -> int:
    """Score a puzzle candidate against a learner message using transparent keywords."""
    query_tokens = _tokens(message)
    if not query_tokens:
        return 0
    candidate_tokens = _tokens(_candidate_text(candidate))
    overlap = query_tokens & candidate_tokens
    score = len(overlap)

    lowered_message = (message or "").lower()
    lowered_title = f"{candidate.get('title', '')} {candidate.get('story_label', '')}".lower()
    for token in query_tokens:
        if token in lowered_title:
            score += 2
    if any(t in lowered_message for t in ("story", "moral", "bedtime", "parable", "fable")):
        score += 1
    return score


def build_context(candidates: list[dict[str, Any]], max_items: int = 2) -> str:
    """Build compact tutor context from already-ranked puzzle candidates."""
    if not candidates:
        return ""

    lines = [
        "Meaning graph context (use as a story, moral, or nature bridge only if it fits):"
    ]
    for row in candidates[:max_items]:
        story = row.get("story_label", "Story")
        tradition = row.get("tradition") or "shared wisdom"
        moral = row.get("moral_tension") or row.get("story_summary") or ""
        motifs = ", ".join(_label_ids(row.get("motif_ids") or []))
        suffix = f" Motifs: {motifs}." if motifs else ""
        lines.append(f"- {story} ({tradition}): {moral}{suffix}")

    first = candidates[0]
    lines.append(
        "Bedtime puzzle suggestion: "
        f"{first.get('title', 'Untitled')}. "
        f"Suspense: {first.get('suspense_question', '')} "
        f"Parent/Parth path: {first.get('parent_hint', '')} "
        f"Nature bridge: {first.get('nature_bridge', '')}"
    )
    return "\n".join(lines)


def _label_ids(ids: list[str]) -> list[str]:
    labels = []
    for raw in ids:
        value = str(raw)
        for prefix in ("motif_", "concept_", "nature_pattern_", "question_"):
            if value.startswith(prefix):
                value = value[len(prefix):]
        labels.append(value.replace("_", " "))
    return labels


async def get_graph(
    conn,
    age: int | str | None = 8,
    tradition: str | None = None,
    limit: int = 260,
) -> dict[str, Any]:
    """Return graph nodes and edges filtered for the UI."""
    age_i = clamp_age(age)
    tradition_f = normalize_filter(tradition)
    rows = await conn.fetch(
        """
        SELECT id, label, kind, tradition, summary, age_min, age_max, tags, metadata
        FROM meaning_graph.nodes
        WHERE age_min <= $1
          AND age_max >= $1
          AND ($2::text IS NULL OR kind <> 'story' OR tradition = $2)
        ORDER BY
          CASE kind
            WHEN 'source' THEN 0
            WHEN 'story' THEN 1
            WHEN 'motif' THEN 2
            WHEN 'concept' THEN 3
            WHEN 'question' THEN 4
            ELSE 5
          END,
          tradition,
          label
        LIMIT $3
        """,
        age_i,
        tradition_f,
        limit,
    )
    nodes = [_row_dict(r) for r in rows]
    node_ids = [n["id"] for n in nodes]
    edges: list[dict[str, Any]] = []
    if node_ids:
        edge_rows = await conn.fetch(
            """
            SELECT from_id, to_id, relation, weight, rationale, metadata
            FROM meaning_graph.edges
            WHERE from_id = ANY($1::text[])
              AND to_id = ANY($1::text[])
            ORDER BY relation, from_id, to_id
            """,
            node_ids,
        )
        edges = [
            {
                "source": r["from_id"],
                "target": r["to_id"],
                "relation": r["relation"],
                "weight": float(r["weight"]),
                "rationale": r["rationale"],
                "metadata": r["metadata"],
            }
            for r in edge_rows
        ]

    return {
        "age": age_i,
        "tradition": tradition_f or "all",
        "nodes": nodes,
        "edges": edges,
        "source": "postgres",
    }


async def get_puzzles(
    conn,
    age: int | str | None = 8,
    tradition: str | None = None,
    motif: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    age_i = clamp_age(age)
    tradition_f = normalize_filter(tradition)
    motif_f = normalize_filter(motif)
    rows = await conn.fetch(
        """
        SELECT p.id, p.story_id, p.title, p.age_min, p.age_max,
               p.setup, p.suspense_question, p.choice_a, p.choice_b, p.choice_c,
               p.parent_hint, p.parth_reasoning, p.moral_tension,
               p.nature_bridge, p.deeper_question, p.concept_ids, p.motif_ids,
               p.metadata, s.label AS story_label, s.tradition,
               s.summary AS story_summary, s.tags AS story_tags
        FROM meaning_graph.story_puzzles p
        JOIN meaning_graph.nodes s ON s.id = p.story_id
        WHERE p.age_min <= $1
          AND p.age_max >= $1
          AND ($2::text IS NULL OR s.tradition = $2)
          AND (
            $3::text IS NULL
            OR $3 = ANY(p.motif_ids)
            OR lower(p.title || ' ' || p.moral_tension || ' ' || p.nature_bridge) LIKE '%' || $3 || '%'
          )
        ORDER BY s.tradition, p.age_min, p.title
        LIMIT $4
        """,
        age_i,
        tradition_f,
        motif_f,
        limit,
    )
    return [_row_dict(r) for r in rows]


async def get_puzzle(conn, puzzle_id: str) -> dict[str, Any] | None:
    rows = await conn.fetch(
        """
        SELECT p.id, p.story_id, p.title, p.age_min, p.age_max,
               p.setup, p.suspense_question, p.choice_a, p.choice_b, p.choice_c,
               p.parent_hint, p.parth_reasoning, p.moral_tension,
               p.nature_bridge, p.deeper_question, p.concept_ids, p.motif_ids,
               p.metadata, s.label AS story_label, s.tradition,
               s.summary AS story_summary, s.tags AS story_tags
        FROM meaning_graph.story_puzzles p
        JOIN meaning_graph.nodes s ON s.id = p.story_id
        WHERE p.id = $1
        LIMIT 1
        """,
        puzzle_id,
    )
    return _row_dict(rows[0]) if rows else None


async def context_for_message(conn, message: str, age: int | str | None = 8) -> str:
    """Retrieve a compact meaning graph context for the tutor prompt."""
    if conn is None or not (message or "").strip():
        return ""
    rows = await get_puzzles(conn, age=age, limit=40)
    scored: list[dict[str, Any]] = []
    for row in rows:
        score = score_candidate(message, row)
        if score > 0:
            scored.append({**row, "_score": score})
    scored.sort(key=lambda r: (-int(r.get("_score", 0)), r.get("title", "")))
    return build_context(scored[:3])


async def neo4j_export(conn) -> dict[str, Any]:
    node_rows = await conn.fetch(
        """
        SELECT id, label, kind, tradition, summary, age_min, age_max, tags
        FROM meaning_graph.nodes
        ORDER BY kind, tradition, label
        """
    )
    edge_rows = await conn.fetch(
        """
        SELECT from_id, to_id, relation, weight, rationale
        FROM meaning_graph.edges
        ORDER BY relation, from_id, to_id
        """
    )
    nodes = [_row_dict(r) for r in node_rows]
    relationships = [
        {
            "source": r["from_id"],
            "target": r["to_id"],
            "relation": r["relation"],
            "weight": float(r["weight"]),
            "rationale": r["rationale"],
        }
        for r in edge_rows
    ]
    return {
        "nodes": nodes,
        "relationships": relationships,
        "cypher": graph_to_cypher(nodes, relationships),
    }


def graph_to_cypher(nodes: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "// Parth meaning graph export",
        "CREATE CONSTRAINT meaning_node_id IF NOT EXISTS FOR (n:MeaningNode) REQUIRE n.id IS UNIQUE;",
    ]
    for node in nodes:
        props = {
            "id": node.get("id", ""),
            "label": node.get("label", ""),
            "kind": node.get("kind", ""),
            "tradition": node.get("tradition", ""),
            "summary": node.get("summary", ""),
            "age_min": int(node.get("age_min", 5)),
            "age_max": int(node.get("age_max", 10)),
            "tags": list(node.get("tags") or []),
        }
        prop_text = ", ".join(f"{key}: {_cypher_value(value)}" for key, value in props.items())
        lines.append(f"MERGE (n:MeaningNode {{id: {_cypher_value(props['id'])}}}) SET n += {{{prop_text}}};")

    for rel in relationships:
        rel_type = _relationship_type(str(rel.get("relation", "RELATED_TO")))
        source_id = _cypher_value(rel.get("source", ""))
        target_id = _cypher_value(rel.get("target", ""))
        lines.append(
            f"MATCH (a:MeaningNode {{id: {source_id}}}), "
            f"(b:MeaningNode {{id: {target_id}}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r.relation = "
            f"{_cypher_value(rel.get('relation', ''))}, "
            f"r.weight = {float(rel.get('weight', 1.0)):.4f}, "
            f"r.rationale = {_cypher_value(rel.get('rationale', ''))};"
        )
    return "\n".join(lines)


def _relationship_type(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value or "RELATED_TO").upper()
    return clean if clean and clean[0].isalpha() else "RELATED_TO"


def _cypher_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_cypher_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return _cypher_quote(json.dumps(value, sort_keys=True))
    return _cypher_quote(str(value or ""))


def _cypher_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f"'{escaped}'"
