// Parth Meaning Graph — schema constraints
//
// Five node labels:
//   Tradition          — a source culture/canon (Aesop, Panchatantra, Bible, ...)
//   Story               — a single story/parable/episode
//   Concept             — a moral/psychological theme a story embodies
//   CharacterArchetype  — a recurring character-shape across traditions
//   DevelopmentalStage  — a phase of a child's meaning-making capacity
//
// Six relationship types:
//   (Story)-[:FROM_TRADITION]->(Tradition)
//   (Story)-[:EMBODIES {centrality: 'primary'|'secondary'}]->(Concept)
//   (Story)-[:FEATURES {role}]->(CharacterArchetype)
//   (Concept)-[:GRASPABLE_AT]->(DevelopmentalStage)
//   (Story)-[:ECHOES {reason}]->(Story)             — cross-tradition kinship
//   (Concept)-[:RELATED_TO {nature, via}]->(Concept) — 'tension'|'reinforcement'
//   (DevelopmentalStage)-[:PRECEDES]->(DevelopmentalStage)

CREATE CONSTRAINT tradition_id IF NOT EXISTS FOR (t:Tradition) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT story_id IF NOT EXISTS FOR (s:Story) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT archetype_id IF NOT EXISTS FOR (a:CharacterArchetype) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT stage_id IF NOT EXISTS FOR (d:DevelopmentalStage) REQUIRE d.id IS UNIQUE;
