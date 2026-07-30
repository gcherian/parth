"""
modules.story_graph.graph — read-side query functions over the Neo4j
meaning graph, in the same style as modules/curriculum_graph/graph.py:
plain functions returning plain data structures, no LLM calls here.
The tutor LLM does the reasoning; this module just retrieves.

This is the "enzyme consulting DNA" surface the agents would call —
not yet wired into the live 15-agent pipeline (see design note), but
every function here is real and tested against the live graph.
"""
from typing import Optional

from neo4j import GraphDatabase

from config import Config

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )
    return _driver


def close():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def get_story(story_id: str) -> Optional[dict]:
    """Full story detail: synopsis, hook, tradition, concepts, archetypes, echoes."""
    query = """
    MATCH (s:Story {id: $id})-[:FROM_TRADITION]->(t:Tradition)
    OPTIONAL MATCH (s)-[e:EMBODIES]->(c:Concept)
    OPTIONAL MATCH (s)-[f:FEATURES]->(a:CharacterArchetype)
    OPTIONAL MATCH (s)-[ec:ECHOES]->(other:Story)
    RETURN s, t.label AS tradition,
           collect(DISTINCT {id: c.id, label: c.label, centrality: e.centrality}) AS concepts,
           collect(DISTINCT {id: a.id, label: a.label, role: f.role}) AS archetypes,
           collect(DISTINCT {id: other.id, title: other.title, reason: ec.reason}) AS echoes
    """
    with _get_driver().session() as session:
        record = session.run(query, id=story_id).single()
        if not record:
            return None
        story = dict(record["s"])
        story["tradition"] = record["tradition"]
        story["concepts"] = [c for c in record["concepts"] if c["id"]]
        story["archetypes"] = [a for a in record["archetypes"] if a["id"]]
        story["echoes"] = [e for e in record["echoes"] if e["id"]]
        return story


def stories_for_stage(stage_id: str, limit: int = 10) -> list[dict]:
    """Stories whose concepts are graspable at this developmental stage."""
    query = """
    MATCH (d:DevelopmentalStage {id: $stage_id})<-[:GRASPABLE_AT]-(c:Concept)<-[e:EMBODIES]-(s:Story)
    RETURN DISTINCT s.id AS id, s.title AS title, s.age_min AS age_min, s.age_max AS age_max,
           s.suspense_hook AS suspense_hook, c.label AS concept, e.centrality AS centrality
    ORDER BY s.age_min
    LIMIT $limit
    """
    with _get_driver().session() as session:
        return [dict(r) for r in session.run(query, stage_id=stage_id, limit=limit)]


def stories_for_concept(concept_id: str) -> list[dict]:
    query = """
    MATCH (c:Concept {id: $concept_id})<-[e:EMBODIES]-(s:Story)-[:FROM_TRADITION]->(t:Tradition)
    RETURN s.id AS id, s.title AS title, t.label AS tradition, e.centrality AS centrality,
           s.age_min AS age_min, s.age_max AS age_max
    ORDER BY e.centrality, s.age_min
    """
    with _get_driver().session() as session:
        return [dict(r) for r in session.run(query, concept_id=concept_id)]


def concept_neighbourhood(concept_id: str) -> dict:
    """Related concepts (tension/reinforcement) — for building a richer context around one idea."""
    query = """
    MATCH (c:Concept {id: $concept_id})
    OPTIONAL MATCH (c)-[r:RELATED_TO]-(other:Concept)
    RETURN c.label AS label, c.description AS description,
           collect(DISTINCT {id: other.id, label: other.label, nature: r.nature, via: r.via}) AS related
    """
    with _get_driver().session() as session:
        record = session.run(query, concept_id=concept_id).single()
        if not record:
            return {}
        return {
            "label": record["label"],
            "description": record["description"],
            "related": [r for r in record["related"] if r["id"]],
        }


def cross_tradition_paths(concept_id: str, max_hops: int = 2) -> list[dict]:
    """
    Stories reachable from a concept within N hops through ECHOES/RELATED_TO —
    "show me the same pattern from a different tradition." This is the
    multi-hop traversal that motivated a real graph DB over single-hop SQL.
    """
    query = f"""
    MATCH (c:Concept {{id: $concept_id}})<-[:EMBODIES]-(start:Story)
    MATCH path = (start)-[:ECHOES*1..{max_hops}]-(reached:Story)
    RETURN DISTINCT reached.id AS id, reached.title AS title, length(path) AS hops
    ORDER BY hops
    """
    with _get_driver().session() as session:
        return [dict(r) for r in session.run(query, concept_id=concept_id)]


def suggest_story_for_open_loop(concept_ids: list[str], age: int, limit: int = 3) -> list[dict]:
    """
    The main integration hook: given concept_ids a learner has shown
    curiosity about (e.g. from learner_state.open_loops.concept_ids or
    a pattern_state signal) and their age, suggest age-appropriate
    stories to plant as tonight's bedtime open loop.
    """
    query = """
    UNWIND $concept_ids AS cid
    MATCH (c:Concept {id: cid})<-[e:EMBODIES]-(s:Story)-[:FROM_TRADITION]->(t:Tradition)
    WHERE s.age_min <= $age <= s.age_max + 2
    RETURN s.id AS id, s.title AS title, t.label AS tradition, c.label AS matched_concept,
           s.suspense_hook AS suspense_hook, e.centrality AS centrality
    ORDER BY CASE e.centrality WHEN 'primary' THEN 0 ELSE 1 END, s.age_min
    LIMIT $limit
    """
    with _get_driver().session() as session:
        return [dict(r) for r in session.run(query, concept_ids=concept_ids, age=age, limit=limit)]
