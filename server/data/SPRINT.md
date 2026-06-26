# Parth — 10-Day Sprint & 8-Week Roadmap
*Generated 2026-05-18 · All answers YES · Proceed autonomously*

---

## The Core Problem

> "How do we understand a child with minimal prior knowledge — when the parents
> don't understand them, the child doesn't understand themselves, and the only
> guides are Parth (AI) and Krishna (conscience)?"

The answer is **sensing through doing**. A child who chooses the astronomy puzzle
over the chemistry puzzle has told you something. A child who takes 90 seconds on
a beginner puzzle but 10 seconds on an advanced one has told you more. Every
interaction is a signal. The job of the first two weeks is to build the sensing
layer — not to teach, but to listen.

---

## What Already Exists (v4.0)

| Layer | Status |
|---|---|
| Learner profile (7-dim psyche, MBTI, emotion, engagement) | ✓ |
| BKT per-concept mastery | ✓ |
| SM-2 spaced repetition | ✓ |
| Krishna Oracle (Claude Haiku background advisor) | ✓ |
| ChromaDB RAG (NCERT curriculum) | ✓ |
| Misconception detection | ✓ |
| Parent dashboard module | ✓ |
| **V2 puzzle library (300 puzzles, 100 thinkers, 10 spheres)** | ✓ (data only) |
| **Puzzle delivery engine** | ✗ ← Day 1 |
| **Sphere/interest affinity tracker** | ✗ ← Day 2 |
| **Cross-subject fusion map** | ✗ ← Day 4 |
| **SAINT/DKT knowledge tracing** | ✗ ← Day 5-6 |
| **Telos engine (goal navigation)** | ✗ ← Day 8 |

---

## 10-Day Sprint — "Understanding the Child"

### Day 1 — Puzzle Engine Module
Build `modules/puzzle_engine/`: loader, selector, response storage, kernel module.
- `GET /puzzle/next/{learner_id}` — ZPD-aware next puzzle
- `POST /puzzle/respond` — store response, trigger evaluation
- SQLite: `puzzle_responses` table
**Output**: A child can receive a puzzle and submit a response. The response is stored.

### Day 2 — Sphere Affinity Tracker
Connect puzzle interactions to the learner's interest graph.
- Every puzzle attempt updates `sphere_affinity[sphere] += engagement_delta`
- EMA smoothing (same as `analogy_scores`)
- Sphere affinity becomes an input to Parth's system prompt
**Output**: Parth knows "this child gravitates toward astronomy, not chemistry."

### Day 3 — ZPD-Aware Puzzle Selector
Upgrade naive selector to Vygotsky ZPD logic:
- Never serve a puzzle 2 levels above current mastery
- Prefer spheres with high affinity AND low mastery (the productive frontier)
- Rotate sphere to prevent monotony (max 2 consecutive same sphere)
- If mastery > 0.75 in sphere: escalate level
**Output**: Puzzle selection is personalised and developmentally appropriate.

### Day 4 — Cross-Subject Fusion Map
Create `data/fusion_map.json`: every concept reachable via ≥ 2 spheres.
Examples:
- Fractions ↔ music (rhythm, time signatures, harmonic series)
- Pi ↔ astronomy (orbital period ratios, Kepler's third law)
- Natural selection ↔ game theory (prisoner's dilemma, ESS)
- Conservation laws ↔ philosophy (Lavoisier ↔ Parmenides: nothing from nothing)
- Graph theory ↔ social science (Euler bridges = social network analysis)
API: `GET /fusion/{concept_id}?sphere={preferred_sphere}` — return best bridge puzzle.
**Output**: Math can be taught through the child's favourite subject.

### Day 5-6 — SAINT/DKT Knowledge Tracing
Replace simplified BKT with a proper Deep Knowledge Tracing model.
Architecture:
- **Model**: SAINT+ (Self-Attentive Knowledge Tracing with elapsed time)
- **Library**: pyKT (open source, MIT license)
- **Pre-training**: EdNet-KT1 dataset (131M interactions, 1.4M students)
- **Fine-tuning**: Local Parth interactions as they accumulate
- **Cold start**: Fallback to existing BKT until 50+ interactions per learner
Input: sequence of (concept_id, response_quality, elapsed_seconds)
Output: p_mastery per concept (continuous 0-1)
**Output**: Knowledge state is more accurate, especially after misconceptions.

### Day 7 — Cold Start Protocol
Design "First 5 Puzzles" onboarding flow:
- Puzzle 1: beginner, random sphere → get baseline
- Puzzle 2: different sphere, same level → measure relative preference
- Puzzle 3: sphere where child spent most time → confirm affinity
- Puzzle 4: adjacent sphere (cross-subject link) → test curiosity transfer
- Puzzle 5: intermediate level in confirmed sphere → calibrate ZPD
After 5 puzzles: learner has a sphere affinity vector, ZPD estimate, and MBTI signal.
**Output**: Parth knows this child better after 15 minutes than most teachers do after a month.

### Day 8 — Telos Engine
Every child needs a purpose (telos). Without it, learning is random.
Build `modules/telos_engine/`:
- At onboarding: Krishna asks 3 questions (not the child — inferred from behaviour)
  1. Which puzzle did the child choose first without being told to? → domain signal
  2. How long did they stay after the "discover" moment? → depth signal
  3. Did they attempt "go_deeper"? → ambition signal
- Infer a provisional telos: "explorer", "builder", "philosopher", "artist", "scientist"
- Every subsequent puzzle selection weighted toward telos-aligned spheres
- Krishna updates telos every 10 interactions based on trajectory
**Output**: Parth teaches toward something, not just in response to questions.

### Day 9 — Moral Compass Layer (Conscience Module)
The user's deepest request: build the moral compass.
- Every sphere has embedded ethical questions (already in silent_lessons)
- Philosophy/Logic, Social Sciences, and Eastern Wisdom puzzles are the primary vehicle
- Build `modules/conscience/`: after every 5th puzzle, surface one "whole vs part" question
  - Mechanistic: "If you remove the engine, do you still have a car?"
  - Vitalistic: "If you remove a cell from your body, is it still alive? Are you still whole?"
- Track the child's responses to ethical dilemmas — feed into psyche model
- The "moral compass" dimension becomes a 8th psyche dimension (alongside the 7 existing)
**Output**: Parth is not just a tutor but a Bildung system — education as character formation.

### Day 10 — Integration + Demo Flow
End-to-end integration:
1. New child arrives → cold start 5 puzzles → sphere affinity + ZPD set
2. Child chats about maths → Parth uses their astronomy interest as a bridge
3. Misconception detected → SM-2 schedules review → Krishna flags to parent
4. Parent dashboard shows: "Rohan is an explorer-type (ENFP), strongest in astronomy,
   working on fractions via orbital period ratios, misconception on division of negatives"
**Output**: Demo-ready MVP for the "understanding the child" problem.

---

## 8-Week Roadmap

| Week | Theme | Deliverable |
|---|---|---|
| 1 | **Sensing** | Puzzle engine, sphere affinity, cold start |
| 2 | **Knowing** | SAINT upgrade, EdNet pre-training, ZPD calibration |
| 3 | **Bridging** | Cross-subject fusion, telos engine, interest graph |
| 4 | **Curriculum** | NCERT graph enrichment, harder concept coverage |
| 5 | **Retention** | Spaced repetition v2 (SM-2 + SAINT joint scheduling) |
| 6 | **Conscience** | Moral compass module, Bildung tracking, ethical dilemma library |
| 7 | **Parents** | WhatsApp weekly digest, alerts, "what is my child good at?" |
| 8 | **Attention** | Telos-driven web search, curated internet for each child's goal |

---

## Neural Architecture: SAINT+

```
Input Sequence (per interaction):
  [exercise_id, concept_id, response_quality, elapsed_s, hint_used]

Encoder (Exercise Stream):
  Embedding(exercise_id) + Embedding(concept_id)
  → Positional encoding
  → N × Self-Attention layers (causal)

Decoder (Response Stream):
  Embedding(response_quality) + elapsed_time_encoding
  → N × Self-Attention layers (causal)
  → N × Cross-Attention layers (attends to encoder output)

Output:
  Linear(d_model → 1) + Sigmoid
  → p_mastery[next concept] ∈ [0, 1]

Parameters:
  d_model = 256, N = 4 layers, heads = 8
  ~2M parameters — runs on CPU at inference
  Training: EdNet-KT1 pre-training (3-4 hours on GPU/MPS)
  Fine-tuning: Parth interactions (incremental, weekly)
```

### Open Source Stack
- **pyKT** (MIT): pre-built SAINT, DKT, AKT, SAKT models
- **torch** + **MPS** (Apple Silicon): local GPU training
- **EdNet-KT1**: 131M interactions, freely downloadable
- **Ollama gemma3:12b**: frontline tutor (already deployed)
- **Claude Haiku**: Krishna Oracle (already deployed)

---

## The Worst-Case Scenario (And How We Survive It)

Parents unavailable / conflicting / oblivious. Child at 8-13, no self-knowledge.
Parth has only interaction data. How do we still understand this child?

**Signal 1 — Time**: How long does the child stay on a puzzle after the "discover"?
  → Depth preference, intrinsic motivation

**Signal 2 — Choice**: Which puzzle does the child pick when given 2 options?
  → Domain affinity (even if they can't articulate it)

**Signal 3 — Error patterns**: Which types of errors recur?
  → Conceptual gaps, not effort gaps

**Signal 4 — Language**: Hindi/English ratio, vocabulary level, metaphor use
  → Background, confidence, abstract thinking development

**Signal 5 — Emotion trajectory**: Does engagement rise or fall within a session?
  → ZPD calibration (too easy → bored, too hard → anxious)

**Signal 6 — Go-Deeper rate**: What % of puzzles does the child attempt go_deeper?
  → Ambition, intellectual appetite, telos signal

These 6 signals, tracked over 50+ interactions, build a portrait more accurate
than any questionnaire — because children reveal themselves through action,
not self-report.

---

## The Vitalistic Principle

> "The whole is more than the sum of parts."
> In mechanistic systems: parts assembled into whole.
> In vitalistic systems: the whole is present in each part.

Applied to education:
- **Mechanistic view**: mathematics + science + arts = education. Teach each separately.
- **Vitalistic view**: every concept contains the whole of knowledge.
  Pi is geometry AND music AND astronomy AND philosophy (Pythagoras).
  Natural selection is biology AND economics AND ethics AND computation.

Parth's job: find the thread that connects the child's deepest interest to every
concept they need to learn. The subject is never the subject — the wonder is the subject.

---

*Next action: Day 1 implementation begins now → `modules/puzzle_engine/`*
