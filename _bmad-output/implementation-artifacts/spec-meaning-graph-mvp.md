# Meaning Graph MVP Spec

Status: complete

## Goal

Create a practical, demo-ready meaning graph that helps Parth and parents navigate durable stories, moral tensions, nature analogies, and bedtime puzzle prompts for children roughly ages 5-10.

## MVP Scope

- Store seeded meaning graph data in Postgres, with an export path for Neo4j.
- Represent sources, stories, motifs, concepts, questions, and nature patterns as graph nodes.
- Connect nodes with typed edges such as `contains`, `teaches`, `asks`, `mirrors`, and `bridges_to`.
- Provide story puzzle prompts that create suspense and curiosity while staying age-appropriate.
- Expose `/meaning` as an evening navigation page with age/tradition/motif filters.
- Expose API endpoints for graph data, puzzles, individual puzzle detail, and Neo4j Cypher export.
- Let `tutor.runtime` receive a compact meaning graph context before generation when the learner asks a related question.

## Non-Goals

- No hard Neo4j runtime dependency in the app server today.
- No long source-text quotations.
- No per-child graph personalization yet beyond age filtering and tutor message matching.

## Acceptance Checks

- Fresh startup applies the meaning graph schema and seed data idempotently.
- `/meaning/graph?age=8` returns nodes and edges.
- `/meaning/puzzles?age=8` returns story puzzle prompts.
- `/meaning/neo4j/export` returns Cypher plus structured nodes/relationships.
- Chat pipeline runs `meaning.graph` before `tutor.runtime` and does not block when the graph query fails.
- Unit tests cover message scoring, context formatting, age mapping, and Cypher escaping.
