"""
Load seed_data.py into Neo4j. Idempotent — every write is a MERGE, so
this is safe to re-run after editing seed_data.py to pick up changes.

Usage:
    source venv/bin/activate
    python3 -m modules.story_graph.load_seed
"""
import os

from neo4j import GraphDatabase

from modules.story_graph import seed_data as sd

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "parth_story_dev")


def load(tx):
    for t in sd.TRADITIONS:
        tx.run("MERGE (t:Tradition {id: $id}) SET t += $props", id=t["id"], props=t)

    for s in sd.STAGES:
        tx.run("MERGE (d:DevelopmentalStage {id: $id}) SET d += $props", id=s["id"], props=s)

    for i in range(len(sd.STAGE_ORDER) - 1):
        tx.run(
            """MATCH (a:DevelopmentalStage {id: $a}), (b:DevelopmentalStage {id: $b})
               MERGE (a)-[:PRECEDES]->(b)""",
            a=sd.STAGE_ORDER[i], b=sd.STAGE_ORDER[i + 1],
        )

    for a in sd.ARCHETYPES:
        tx.run("MERGE (a:CharacterArchetype {id: $id}) SET a += $props", id=a["id"], props=a)

    for c in sd.CONCEPTS:
        tx.run("MERGE (c:Concept {id: $id}) SET c += $props", id=c["id"], props=c)

    for cid, stages in sd.CONCEPT_STAGES.items():
        for st in stages:
            tx.run(
                """MATCH (c:Concept {id: $cid}), (d:DevelopmentalStage {id: $st})
                   MERGE (c)-[:GRASPABLE_AT]->(d)""",
                cid=cid, st=st,
            )

    for a, b, nature, via in sd.CONCEPT_RELATIONS:
        tx.run(
            """MATCH (c1:Concept {id: $a}), (c2:Concept {id: $b})
               MERGE (c1)-[r:RELATED_TO]->(c2)
               SET r.nature = $nature, r.via = $via""",
            a=a, b=b, nature=nature, via=via,
        )

    for s in sd.STORIES:
        story_props = {k: v for k, v in s.items() if k not in ("tradition", "embodies", "features")}
        tx.run("MERGE (s:Story {id: $id}) SET s += $props", id=s["id"], props=story_props)

        tx.run(
            """MATCH (s:Story {id: $sid}), (t:Tradition {id: $tid})
               MERGE (s)-[:FROM_TRADITION]->(t)""",
            sid=s["id"], tid=s["tradition"],
        )

        for cid, centrality in s["embodies"]:
            tx.run(
                """MATCH (s:Story {id: $sid}), (c:Concept {id: $cid})
                   MERGE (s)-[r:EMBODIES]->(c)
                   SET r.centrality = $centrality""",
                sid=s["id"], cid=cid, centrality=centrality,
            )

        for aid, role in s["features"]:
            tx.run(
                """MATCH (s:Story {id: $sid}), (a:CharacterArchetype {id: $aid})
                   MERGE (s)-[r:FEATURES]->(a)
                   SET r.role = $role""",
                sid=s["id"], aid=aid, role=role,
            )

    for a, b, reason in sd.ECHOES:
        tx.run(
            """MATCH (s1:Story {id: $a}), (s2:Story {id: $b})
               MERGE (s1)-[r:ECHOES]->(s2)
               SET r.reason = $reason""",
            a=a, b=b, reason=reason,
        )


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.execute_write(load)

        counts = session.run(
            """
            CALL () {
                MATCH (t:Tradition) RETURN count(t) AS n, 'Tradition' AS label
                UNION ALL MATCH (s:Story) RETURN count(s) AS n, 'Story' AS label
                UNION ALL MATCH (c:Concept) RETURN count(c) AS n, 'Concept' AS label
                UNION ALL MATCH (a:CharacterArchetype) RETURN count(a) AS n, 'CharacterArchetype' AS label
                UNION ALL MATCH (d:DevelopmentalStage) RETURN count(d) AS n, 'DevelopmentalStage' AS label
            }
            RETURN label, n ORDER BY label
            """
        )
        for record in counts:
            print(f"  {record['label']}: {record['n']}")

        rel_counts = session.run(
            """
            CALL () {
                MATCH ()-[r:EMBODIES]->() RETURN count(r) AS n, 'EMBODIES' AS label
                UNION ALL MATCH ()-[r:FEATURES]->() RETURN count(r) AS n, 'FEATURES' AS label
                UNION ALL MATCH ()-[r:ECHOES]->() RETURN count(r) AS n, 'ECHOES' AS label
                UNION ALL MATCH ()-[r:RELATED_TO]->() RETURN count(r) AS n, 'RELATED_TO' AS label
                UNION ALL MATCH ()-[r:GRASPABLE_AT]->() RETURN count(r) AS n, 'GRASPABLE_AT' AS label
                UNION ALL MATCH ()-[r:FROM_TRADITION]->() RETURN count(r) AS n, 'FROM_TRADITION' AS label
            }
            RETURN label, n ORDER BY label
            """
        )
        for record in rel_counts:
            print(f"  {record['label']}: {record['n']}")

    driver.close()
    print("Seed load complete.")


if __name__ == "__main__":
    main()
