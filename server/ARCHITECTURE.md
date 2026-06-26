# Parth Platform — Architecture v2.0
## Microkernel with Event-Driven Backbone

---

## Why this architecture

The v1 design was a pipeline: request in, RAG → route → LLM → evaluate → log → response out.
That works for a prototype. It breaks when:

- A new module (practice.engine) needs to intercept an interaction mid-flight
- Parental consent must gate every data write across every module
- A module update should not require touching the orchestrator
- You want to replay last week's interactions through a new learner.state algorithm
- A child's data must be deletable from every module atomically

The microkernel fixes all of these. The kernel knows nothing about curriculum or
learner psychology — it only routes events between modules that do. Each module
owns its slice completely: its schema, its store, its invariants, its failure modes.

---

## Three-layer structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  L3 — Modules (domain-owned, pluggable, independently deployable)   │
│  curriculum.graph  learner.state  tutor.runtime  practice.engine    │
│  attention.federated  parent.dashboard  moderation.ops  [eighth]    │
├─────────────────────────────────────────────────────────────────────┤
│  L2 — Microkernel: Tutor Orchestrator                               │
│  Stateless · Transactional · Idempotent · Event-routing only        │
├─────────────────────────────────────────────────────────────────────┤
│  L1 — Foundation                                                    │
│  Postgres + Event Outbox  ·  Object Store  ·  Identity             │
│  Observability  ·  Shared event schema                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## L1 — Foundation

### 1.1 Postgres + Event Outbox

All state lives in Postgres. All state changes are events.

The outbox pattern makes event publishing atomic with the business write:

```sql
-- Every module writes to its own tables AND to outbox in ONE transaction
BEGIN;
  INSERT INTO learner_state.knowledge (learner_id, concept_id, p_mastery) VALUES (...);
  INSERT INTO foundation.outbox (event_type, payload, status)
    VALUES ('learner.knowledge_updated', '{"learner_id":...}', 'pending');
COMMIT;
-- A background relay picks up pending outbox rows and delivers to subscribers
```

No outbox row = no event = no subscriber update. The outbox survives crashes; no
event is lost, no event is delivered without a matching DB write.

**Outbox schema:**
```sql
CREATE TABLE foundation.outbox (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type  TEXT NOT NULL,            -- 'tutor.interaction_completed', etc.
  aggregate   TEXT,                     -- 'learner', 'session', 'concept'
  aggregate_id TEXT,                   -- the learner_id / session_id
  payload     JSONB NOT NULL,
  status      TEXT DEFAULT 'pending',  -- pending | delivered | failed
  created_at  TIMESTAMPTZ DEFAULT now(),
  delivered_at TIMESTAMPTZ
);
CREATE INDEX ON foundation.outbox (status, created_at) WHERE status = 'pending';
```

**Relay:** A single-threaded Postgres LISTEN/NOTIFY relay (or a pg_cron job every
100ms) picks up pending rows, delivers to in-process module subscribers, marks
delivered. For multi-instance deployments, use `FOR UPDATE SKIP LOCKED`.

### 1.2 Object Store

All binary content (NCERT PDFs, audio clips, diagrams, child-drawn images) lives
in an S3-compatible object store (local: MinIO; production: Cloudflare R2).

Modules never write files to disk. They call `object_store.put(key, bytes)` and
store the key in Postgres. URLs are signed, short-lived.

**Namespacing:**
```
ncert/{grade}/{subject}/{chapter}.pdf
learner/{learner_id}/drawings/{session_id}/{ts}.png
practice/{concept_id}/questions/{q_id}.json
```

### 1.3 Identity — Parental Consent Aware

Every learner has an identity record. Children under 13 (COPPA, India DPDP Act)
require a linked guardian with active consent.

**Consent model:**
```sql
CREATE TABLE foundation.identities (
  id          UUID PRIMARY KEY,
  type        TEXT,   -- 'child' | 'guardian' | 'teacher'
  grade       INT,
  birth_year  INT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE foundation.guardian_links (
  guardian_id UUID REFERENCES foundation.identities,
  child_id    UUID REFERENCES foundation.identities,
  consent_given BOOLEAN DEFAULT false,
  consent_ts  TIMESTAMPTZ,
  scope       TEXT[]   -- ['learner_data', 'ai_interaction', 'progress_report']
);
```

**Consent gate:** Every module that processes child data calls
`identity.check_consent(learner_id, scope)` before writing. If consent is missing
or revoked, the write is blocked and a `consent.required` event is published.

**Right to erasure:** `identity.erase(learner_id)` cascades through all module
schemas via FK constraints + a dedicated `on_erase` hook each module registers.

### 1.4 Observability

All L2 and L3 code emits structured telemetry via three channels:

- **Traces** (OpenTelemetry): every request → kernel span → child spans per module
- **Metrics** (Prometheus): request latency, token count, p_mastery distributions,
  emotion state histogram, module error rates
- **Logs** (structured JSON to stdout, shipped by log collector): every event,
  every module call, every outbox delivery

Kernel adds `trace_id` and `request_id` to every event. All module logs include
both. A single `trace_id` reconstructs the full interaction across modules.

---

## L2 — Microkernel: Tutor Orchestrator

### What the kernel knows

The kernel knows:
- Which event types exist
- Which modules handle which event types (the routing table)
- How to load/save idempotency keys
- How to open/commit Postgres transactions
- How to call a module's `handle()` method

The kernel does NOT know:
- What a curriculum graph is
- What p_mastery means
- What Gemma or Ollama is
- What a parent report contains

### Routing table

```python
ROUTING_TABLE = {
    "interaction.requested": [
        # Phase 1 — parallel pre-processing
        Parallel([
            "moderation.ops",      # safety check on input
            "learner.state",       # load child context
            "curriculum.graph",    # retrieve concept graph neighbourhood
        ]),
        # Phase 2 — generation
        Sequential([
            "tutor.runtime",       # build prompt, call LLM, get response
        ]),
        # Phase 3 — parallel post-processing
        Parallel([
            "moderation.ops",      # safety check on output
            "practice.engine",     # log interaction for spaced repetition
        ]),
    ],
    "practice.session_requested": [
        Sequential(["learner.state", "curriculum.graph", "practice.engine"]),
    ],
    "parent.report_requested": [
        Sequential(["learner.state", "parent.dashboard"]),
    ],
}
```

### Stateless protocol

Every kernel invocation:
1. Receives a `KernelRequest` (HTTP or internal)
2. Generates or validates `request_id` (UUID v4)
3. Checks idempotency table — if `request_id` seen before, returns cached result
4. Opens a Postgres transaction
5. Publishes `interaction.requested` to outbox (in-transaction)
6. Calls modules per routing table
7. Collects `KernelResponse` from final module
8. Writes idempotency record + outbox `interaction.completed`
9. Commits transaction
10. Returns response

No in-memory state survives beyond step 10. Crash after step 4, replay from step 3.

### Module interface contract

Every L3 module implements:

```python
class Module(ABC):
    name: str          # e.g. "curriculum.graph"
    handles: list[str] # event types this module processes

    @abstractmethod
    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        """
        Called by kernel. Must be idempotent on event.request_id.
        ctx provides: db connection (in-kernel transaction), identity,
        object_store, trace span.
        Returns: data dict merged into KernelContext for downstream modules.
        Raises: ModuleError (kernel catches, publishes error event, continues or aborts).
        """

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        """Right-to-erasure hook. Called by identity module cascade."""
        pass
```

### Idempotency

```sql
CREATE TABLE foundation.idempotency (
  request_id  UUID PRIMARY KEY,
  response    JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);
-- TTL: clean up rows older than 24h
```

If a retry arrives with the same `request_id`, return `response` immediately.
No module is called twice for the same interaction.

### Transactions and module failures

- If `moderation.ops` blocks input → transaction aborts, `interaction.blocked` event
- If `tutor.runtime` times out → transaction aborts, `interaction.failed` event, client gets retry instruction
- If a post-processing module fails → transaction commits (child gets their answer), `module.error` event triggers alerting

The child's answer is never withheld because a background analytics module failed.

---

## L3 — Modules

### curriculum.graph

**Owns:** NCERT concept graph — nodes are concepts, edges are prerequisites/co-requisites.

**Responsibility:**
- Store and traverse the curriculum as a graph (Postgres + `ltree` or adjacency list)
- Given a concept mention, return its neighbourhood: prerequisites the child should know, co-concepts, what comes next
- Feed `curriculum_context` into kernel context for `tutor.runtime`
- Detect when a child's question implies a prerequisite gap

**Events consumed:** `interaction.requested`
**Events published:** `curriculum.context_retrieved`, `prerequisite.gap_detected`

**Key tables:** `concept(id, label, subject, grade_range, description)`, `concept_edge(from_id, to_id, type)`

---

### learner.state

**Owns:** All 15 learner dimensions. The growing portrait of this child.

**Responsibility:**
- Load full learner context for kernel (O(1) read from Postgres)
- Accept `learner.signals` events and update all dimensions atomically
- Expose `build_prompt_context()` — the concise child-context string for tutor.runtime
- Emit `learner.milestone_reached` when mastery crosses thresholds
- Implement `on_erase` completely

**Events consumed:** `interaction.completed`, `practice.answered`
**Events published:** `learner.state_updated`, `learner.milestone_reached`, `learner.struggling` (3 misconceptions on same concept)

**Key tables:** `learner_profile`, `knowledge_state`, `misconception_map`, `analogy_scores`, `emotion_history`

---

### tutor.runtime

**Owns:** Everything that touches an LLM — prompt assembly, model selection, inference, streaming.

**Responsibility:**
- Receive `KernelContext` (curriculum context + learner context + history)
- Build the final system prompt by assembling all context slices
- Route to model (gemma3:12b vs llama3.2) based on complexity signals
- Call Ollama, handle timeouts and fallback
- Return `TutorResponse` — raw text + model metadata

**Events consumed:** kernel calls it synchronously (it is in the critical path)
**Events published:** `tutor.response_generated` (payload includes token count, model, latency)

This module is the only one that knows Ollama exists. All other modules are LLM-agnostic.

---

### practice.engine

**Owns:** Question generation, exercise sessions, spaced repetition scheduling.

**Responsibility:**
- Generate practice questions for a concept using SM-2 spaced repetition
- Schedule next review based on learner's last answer and p_mastery
- Track correct/incorrect answers and feed signals back to learner.state
- Detect when a child is ready to move to the next concept in curriculum.graph

**Events consumed:** `interaction.completed`, `learner.milestone_reached`
**Events published:** `practice.question_ready`, `practice.concept_cleared`

**Key tables:** `practice_card(learner_id, concept_id, next_review, interval, ease_factor)`, `practice_answer(learner_id, concept_id, correct, ts)`

---

### attention.federated

**Owns:** Aggregate learning-signal processing across the learner population, without centralising raw data.

**Responsibility:**
- Maintain population-level priors on concept difficulty, common misconception prevalence, and effective analogy mappings
- These priors flow back into `learner.state` to improve cold-start for new learners
- Differential privacy budget tracked per learner — no individual can be re-identified from aggregates
- Federated: runs locally per deployment, only aggregate gradients are shared if opted in

**Events consumed:** `learner.state_updated` (anonymised signal)
**Events published:** `attention.priors_updated`

---

### parent.dashboard

**Owns:** All parent-facing data surfaces. Nothing parent-facing exists outside this module.

**Responsibility:**
- Compose weekly progress digests from `learner.state` events
- Consent management UI hooks (approve / revoke / modify scope)
- Alert parents when `learner.struggling` event fires
- Export learner data in human-readable form on request
- Gate: checks `identity.consent` before any write to its tables

**Events consumed:** `learner.milestone_reached`, `learner.struggling`, `interaction.completed` (summary)
**Events published:** `parent.report_generated`, `parent.consent_updated`

---

### moderation.ops

**Owns:** Content safety — both input (child's message) and output (Parth's response).

**Responsibility:**
- Input check: detect harmful content, PII, distress signals ("I want to hurt myself")
- Output check: ensure response is age-appropriate and on-curriculum
- NCPCR guideline compliance tagging
- When distress is detected: suppress LLM response, return a pre-approved safe message + flag for human review
- Operates in the critical path (kernel waits for its clearance)

**Events consumed:** called synchronously by kernel pre- and post-generation
**Events published:** `moderation.input_blocked`, `moderation.distress_detected`, `moderation.output_flagged`

**Important:** This module has veto power. It is the only module that can abort a kernel transaction unilaterally.

---

### [Eighth module — TBD]

Seven modules are named. The eighth slot is reserved. Candidates:
- `assessment.adaptive` — formal assessment, mock tests, board-exam preparation
- `content.studio` — teacher/parent content creation tools
- `social.peer` — classroom cohort features, group learning sessions

---

## Event schema — shared definitions

```python
@dataclass
class Event:
    id:          UUID        # unique event ID
    request_id:  UUID        # ties all events in one interaction together
    trace_id:    UUID        # OpenTelemetry trace
    type:        str         # 'interaction.requested', 'learner.state_updated', etc.
    aggregate:   str         # 'learner' | 'session' | 'concept'
    aggregate_id: str        # the primary key of the aggregate
    payload:     dict        # event-specific data
    schema_ver:  int         # for forward compatibility
    ts:          datetime

@dataclass
class KernelContext:
    request_id:       UUID
    learner_id:       str
    learner_context:  str        # built by learner.state
    curriculum_context: str      # built by curriculum.graph
    history:          list[dict]
    subject:          str
    grade:            int
    moderation_ok:    bool
    module_data:      dict[str, Any]  # accumulates as modules run
```

---

## Implementation roadmap

### Sprint 1 — Foundation swap (this sprint)
- Replace SQLite with Postgres (local Docker for dev)
- Implement outbox table + relay
- Implement identity + guardian_link tables (no consent UI yet)
- Wire observability: structured JSON logs + request_id/trace_id on every log line

### Sprint 2 — Kernel skeleton
- `KernelContext` and `ModuleResult` dataclasses
- Routing table (hardcoded, no plugin discovery yet)
- Idempotency table + check
- Refactor current pipeline into kernel calling learner.state + tutor.runtime

### Sprint 3 — Module extraction
- Extract curriculum.graph (replace ChromaDB retriever with graph-aware retriever)
- Extract moderation.ops (currently implicit; make it explicit with veto)
- Extract practice.engine (new — SM-2 scheduling)

### Sprint 4 — Parent + identity flows
- Guardian consent flow (mobile + web)
- parent.dashboard event consumers + report API
- Right-to-erasure cascade

### Sprint 5 — Federated attention
- Population priors for concept difficulty
- Cold-start prior injection into learner.state

---

## What does NOT change

- Ollama running locally on M2 Pro — tutor.runtime owns this, nothing else changes
- Flutter app interface — the `/chat` HTTP endpoint stays; kernel is behind it
- NCERT RAG content — moves into curriculum.graph module
- The 15 learner dimensions — owned by learner.state module
- The phone-first UX — all of this is server-side plumbing
