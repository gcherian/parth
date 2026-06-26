# Parth Learner Model — Design Specification v1.0

## Why this exists

RAG gives Parth knowledge of the curriculum.
The learner model gives Parth knowledge of the child.

Without it, every session starts cold. A child who has asked about photosynthesis
six times still gets a generic explanation. A child who lights up at cricket analogies
gets cooking examples. A child who is frustrated gets the same cheerful tone as a
child who is excited.

The learner model accumulates a growing portrait of *this specific child* that
shapes every word Parth produces.

---

## The 15 dimensions and their implementation tier

| # | Dimension | Tier | Inference source |
|---|---|---|---|
| 01 | Knowledge state | 1 | Concept mentions + misconception signals |
| 02 | Misconception map | 1 | Evaluator LLM after every response |
| 03 | Cognitive profile | 2 | Reading level from messages, WM from retention |
| 04 | Productive-struggle window | 2 | Time between question and reply |
| 05 | Per-concept learning speed | 2 | BKT acquisition rates over sessions |
| 06 | Motivational profile | 1 | Topic engagement signals from message patterns |
| 07 | Sessional emotion | 1 | Evaluator LLM + heuristic signals |
| 08 | Stress signature | 3 | Multi-dimensional, requires longitudinal data |
| 09 | Effort-vs-ability attribution | 2 | Explicit probe + language signals |
| 10 | Linguistic register | 1 | Character-level language detection |
| 11 | Confidence calibration | 2 | Explicit probe before Parth confirms |
| 12 | Family context | 3 | Onboarding survey |
| 13 | Chrono-learning pattern | 3 | Session timestamp distribution |
| 14 | Social-learning preference | 3 | Onboarding survey |
| 15 | Analogy-domain preference | 1 | Keyword engagement tracking |

---

## Tier 1 — What we build now

Six dimensions inferred from every message exchange, zero extra questions asked.

### 01 Knowledge state

**What it is:** Per-concept probability of mastery, updated Bayesian-style.

**Schema:** `knowledge_state JSON` — map from concept_id to:
```json
{ "p_mastery": 0.6, "exposures": 4, "misconceptions": 1, "demonstrations": 2 }
```

**Update rules:**
- Child asks about a concept → `exposures += 1`, `p_mastery` nudged down slightly
- Evaluator finds misconception about concept → `misconceptions += 1`, `p_mastery` drops
- Child uses concept correctly in context → `demonstrations += 1`, `p_mastery` rises
- Formula: `p_mastery = demonstrations / max(1, exposures) * (1 - 0.4 * misconceptions / max(1, exposures))`

**Prompt injection:** "Weak concepts to reinforce: [list]", "Solid foundation on: [list]"

### 02 Misconception map

**What it is:** Structured map of wrong beliefs, tied to specific concepts.

**Schema:** `misconception_map JSON` — map from concept_id to list of misconception strings.

**Update rules:** Evaluator output → parse concept from misconception text → append.

**Prompt injection:** "Known misconceptions to gently correct if relevant: [list]"

### 06 Motivational profile

**What it is:** Which topics, subjects, and question types produce engagement spikes.

**Schema:** `motivational_profile JSON` — map from topic_id to engagement score (float 0–10).

**Update rules:** After each message, measure engagement (evaluator returns score 1–10).
High engagement (≥7) on a topic → that topic's score rises. Low (<4) → falls.
Exponential moving average: `score = 0.7 * old_score + 0.3 * new_signal`

**Prompt injection:** "High-engagement topics: [top 3]"

### 07 Sessional emotion

**What it is:** Short-window estimate of the child's current emotional state.

**States:** curious · confused · frustrated · excited · neutral · disengaged

**Inference:** Single evaluator LLM call per exchange returns `{emotion, engagement}`.
Heuristic pre-filter (fast, no LLM): short message (<6 words) + no punctuation →
candidate "disengaged". Multiple ! → candidate "excited". "don't get it"/"stuck" →
candidate "confused". LLM call validates and refines.

**Prompt injection:** Drives *tone* of Parth's response. confused → more steps,
simpler words. excited → build on that energy. disengaged → shorter response, ask
a direct question to re-hook.

### 10 Linguistic register

**What it is:** English vs Hindi preference, measured per message, smoothed over sessions.

**Schema:** `language_ratio REAL` — 1.0 = all English, 0.0 = all Hindi.

**Inference:** Count Devanagari codepoints (U+0900–U+097F) vs total word characters
in each message. Exponential moving average: `ratio = 0.8 * old + 0.2 * new_sample`.

**Prompt injection:** Overrides the system prompt language rule — if ratio < 0.4, Parth
defaults to Hindi with English key terms.

### 15 Analogy-domain preference

**What it is:** Which real-world domains (cricket, cooking, festival…) this child
responds to. Used to select examples that land.

**Schema:** `analogy_scores JSON` — map from domain_id to score (float 0–10).

**Inference:** After Parth's response, detect which analogy domains were mentioned
(keyword match). On the child's *next* message, measure engagement. High engagement
→ credit those domains. This is a 1-lag attribution model.

**Prompt injection:** "Use analogies from: cricket, cooking (child responds well to these)"

---

## Schema additions to `learners` table

```sql
knowledge_state      TEXT DEFAULT '{}'   -- {concept_id: {p_mastery, exposures, misconceptions, demonstrations}}
misconception_map    TEXT DEFAULT '{}'   -- {concept_id: [string, ...]}
motivational_profile TEXT DEFAULT '{}'   -- {topic_id: score}
last_emotion         TEXT DEFAULT 'neutral'
engagement_score     REAL DEFAULT 5.0
language_ratio       REAL DEFAULT 1.0
analogy_scores       TEXT DEFAULT '{}'   -- {domain_id: score}
```

---

## Signal extraction pipeline (per exchange)

```
Student message arrives
       │
       ├─► Language detector   → language_ratio sample
       ├─► Concept detector    → list of concept_ids mentioned
       └─► Analogy detector    → list of domains mentioned (for lag attribution)

LLM generates response
       │
       └─► Enhanced evaluator (background, llama3.2)
                │
                ├─► misconception + concept_id
                ├─► emotion (6-class)
                └─► engagement (1–10)

Background update
       │
       ├─► knowledge.update(concept_ids, misconception, demonstration_signal)
       ├─► profile.update_emotion(emotion, engagement)
       ├─► profile.update_language(ratio)
       ├─► profile.update_analogy_scores(prev_domains, engagement)
       └─► logger.log(...)
```

---

## Prompt injection — learner context block

Injected between the base system prompt and the curriculum RAG context:

```
Child profile: {name}, Grade {grade}
Emotional state: {emotion} | Engagement: {engagement}/10
Language: responds in {'English' if ratio > 0.6 else 'Hindi mix'}
Concepts needing reinforcement: {weak_concepts[:3]}
Known misconceptions: {misconceptions[:3]}
Best analogy domains: {top_analogy_domains[:2]}
High-engagement topics: {motivational_profile_top[:2]}
```

---

## Analogy domain library

Seven domains, each with detection keywords and bridgeable curriculum concepts:

| Domain | Keywords | Bridges to |
|---|---|---|
| cricket | cricket bat ball wicket run over | velocity, projectile, friction, statistics |
| cooking | roti dal chai cooker boil fry | heat, fractions, ratios, chemical reactions |
| festival | diwali holi eid diya firework colour | light, optics, chemistry |
| nature | monsoon rain river mountain cloud | water cycle, evaporation, ecosystem |
| transport | auto rickshaw bus train bicycle | force, friction, motion, energy |
| gaming | game phone app level score | probability, logic, electricity |
| farming | crop field harvest seed irrigation | biology, soil, water, seasons |

---

## What the child experiences

**Session 1:** Generic Parth, NCERT-grounded.

**Session 3:** Parth knows you had a photosynthesis misconception. Weaves in a
correction naturally: "And remember — plants need CO₂ too, not just sunlight!"

**Session 8:** Parth has learned you love cricket. Introduces velocity via a bouncer.
Spots you are confused (short terse replies) and shifts to smaller steps.

**Session 15:** Parth opens with: "Last time you were working on fractions —
want to try one quick problem before we move on?" Targeted, not generic.

---

## What we are NOT doing in Tier 1

- No explicit quizzing (Parth probes conversationally, not like a test)
- No persistent sessions (each HTTP request is stateless; state lives in SQLite)
- No ML model training (all inference is heuristic + LLM prompting)
- No v0.3 dimensions (stress signature, family context, chrono-pattern, social pref)
