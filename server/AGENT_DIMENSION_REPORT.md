# The 15-Agent Harness vs. the 15 Child Dimensions

Research report — 2026-07-06. Verified directly against source (`kernel/agent.py`,
`kernel/agent_harness.py`, `kernel/orchestrator.py`, `modules/learner_state/module.py`,
`modules/learner_state/agents/__init__.py`), not inferred.

## 1. Where is "the agency"?

There is no single supervisor agent. The agency is a **deterministic pipeline**, not a
manager:

```
Orchestrator (kernel/orchestrator.py)
  — stateless microkernel: idempotency check → open Postgres transaction →
    route the event through Router to modules → commit → return.
  — knows nothing about psychology, curriculum, or the 15 agents at all.
        │
        ▼
Router → LearnerStateModule (modules/learner_state/module.py)
  — owns a single module-level AgentHarness singleton, built once at import time:
    `_harness = AgentHarness(build_agent_registry())`
        │
        ▼
AgentHarness (kernel/agent_harness.py)
  — the actual dispatch loop. Runs the 15 registered agents in a fixed,
    dependency-encoded order, twice per chat turn (see below).
```

Every chat turn calls `LearnerStateModule.handle()` **twice** — once before the LLM
generates a reply, once after:

- **Phase 1 (pre-generation):** `harness.build_context_traced()` runs all 15 agents'
  `read()` sequentially. Each agent returns a short text snippet describing what it knows
  about this child; all 15 snippets are joined into one string, which becomes part of the
  actual prompt sent to the tutor LLM. This is literally how the agents "talk to the
  tutor" — not an API call, a paragraph each.
- **Phase 3 (post-generation):** `harness.dispatch()` runs all 15 agents' `observe()`
  (write new state to their own DB tables) then `emit()` (publish events), in the same
  fixed order.

Resilience: every agent extends `BaseAgent`, which wraps `_observe()`/`_read()` in
try/except with structured logging (`agent_observe_failed` / `agent_read_failed`). One
agent throwing never breaks the turn or blocks the other 14 — it just logs a warning and
returns an empty result.

Observability: the orchestrator's response payload includes `_agent_trace` — the full
read-trace and dispatch-trace, including a snapshot of the event bus after each agent
runs. This already exists for `observer.html` (the investor/debug demo) — every claim in
this report can be watched live, turn by turn.

## 2. How do the 15 agents communicate with each other?

Two channels, both confirmed in code:

**A. A shared, ephemeral, same-turn event bus** (`AgentSignals.events`, a plain dict on
the shared signals object passed through `dispatch()`). Agents run in a fixed order; an
agent can `emit()` a typed event (e.g. `distress.detected`, `lang.preference`) that any
*later* agent in the same pass can read off `signals.events` before deciding what to do.
This is one-directional (upstream → downstream within one turn) and is exactly why
registration order in `build_agent_registry()` matters — it's a dependency order, not an
alphabetical one:

`EmotionCompass → CurriculumCartographer → MasteryTracker → MisconceptionHunter →
LanguageBridge → BeliefCoach → ChallengeCalibrator → MemoryKeeper → TransferWeaver →
RegisterTuner → HumorDelightGuide → InquiryAlchemist → FamilyAlliance →
RhythmTimeSteward → PatternCreationGuide`

Concretely: EmotionCompass runs first and can emit a distress signal; by the time
HumorDelightGuide and ChallengeCalibrator run later in the *same* turn, they can already
see it and back off a joke or ease difficulty — same-turn, not next-turn.

**B. Persistent cross-turn state via Postgres.** Each agent owns its own table(s)
(`affect_state`, `knowledge`, `misconception_map`, `challenge_state`, `episodes`,
`analogy_history`, `register_state`, `delight_state`, `inquiry_state`, `family_context`,
`rhythm_state`, `pattern_state`, `kt_events`, plus the shared `profiles`/`psyche`). Any
agent's `_read()`/`_observe()` can query any other agent's table directly — this is how
state persists and compounds *across* sessions, not just within one turn.

## 3. Mapping to the 14 (+1) named child dimensions

The user's list from 2026-07-06 morning had 14 items despite being introduced as "15" —
flagged, not silently padded. Working hypothesis for the 15th, reasoned from a gap in the
pattern (nothing else covers how a child learns *with others*) and a matching dormant
implementation found during the codebase audit: **Social Learning & Collaboration**.

| # | Dimension | Primary agent(s) | How |
|---|---|---|---|
| 1 | Cognitive Ability | *(proposed: the 5 cold-start puzzle probes, not a per-message agent)* | Domain-general reasoning, measured before any subject content — cleanly separates this from #6 below |
| 2 | Curiosity and Exploration | InquiryAlchemist, PatternCreationGuide, EmotionCompass (curiosity component) | Curiosity threads + cross-domain "wonder questions" + real-time curiosity probability |
| 3 | Attention and Focus | RhythmTimeSteward | Peak-focus hour estimate, session pacing/fatigue via exponential blend |
| 4 | Memory and Retention | MemoryKeeper | SM-2 spaced repetition + episodic memory (breakthroughs/struggles) |
| 5 | Learning Velocity | **Gap** — no live agent | Nearest concept was in now-superseded code; needs redesign as time-to-mastery normalized against MasteryTracker's ZPD distance, not a flat ratio |
| 6 | Conceptual Understanding and Depth | MasteryTracker | Per-concept `p_mastery` (BKT-style), depth *within* taught material |
| 7 | Problem Solving and Critical Thinking | ChallengeCalibrator, MisconceptionHunter (partial/proxy only) | Struggle calibration + flawed-reasoning detection; nothing measures this directly yet |
| 8 | Creativity and Imagination | PatternCreationGuide (partial/proxy only) | Cross-domain connections is the closest analog, not a direct measure |
| 9 | Motivation and Drive | **Gap** — no live agent | Needs a new signal: voluntary-return cadence under difficulty, derivable from existing session timestamps, not yet computed anywhere |
| 10 | Emotional Well Being and Family Environment | EmotionCompass + FamilyAlliance | Real-time affect vector (frustration/confusion/boredom/curiosity/delight) + consent-gated home context, cleanly split |
| 11 | Confidence and Self Efficacy | BeliefCoach | Confidence-vs-actual-mastery gap, growth-mindset coaching (sole writer of `psyche`) |
| 12 | Adaptability and Resilience | ChallengeCalibrator (partial/proxy only) | Productive-failure tolerance is the closest analog |
| 13 | Learning Preference | RegisterTuner + LanguageBridge + TransferWeaver | Tone/formality/language-mix/preferred-domain preference, collectively — not a VARK-style modality classifier |
| 14 | Value and Purpose | **Total gap, and structurally different** | Doesn't fit the per-message agent pattern at all — shows up in open-ended reflection, not turn-by-turn signals. Needs a periodic reflective prompt read by an LLM pass, closer to the teacher-portrait pattern than a micro-agent |
| 15 (proposed) | Social Learning & Collaboration | *(dormant — `social_preference.py`, currently unwired)* | Group vs. solo preference, peer-interaction pattern — a real dormant implementation exists, wrongly filed as redundant during the first cleanup pass; worth reviving on its own terms |

**Known overlap, resolved above rather than left flagged:** Cognitive Ability and
Conceptual Understanding & Depth previously collapsed onto the same single agent
(MasteryTracker). Splitting the data source — puzzle-probe performance (domain-general,
pre-content) vs. MasteryTracker's per-concept mastery (domain-specific, post-content) —
resolves this for real instead of accepting a duplicate label.

## 4. How this actually shapes curiosity, motivation, and emotional balance today

**Curiosity:** `InquiryAlchemist` tracks open curiosity threads and reads the emotion/
mastery events emitted earlier in the same turn to decide when to nudge deeper;
`PatternCreationGuide` runs *last* in dispatch order specifically so it can synthesize
across everything upstream (episodes, curiosity threads, mastery) into a cross-domain
"wonder question," written to `open_loops` — a table explicitly designed to bring a child
back to an unfinished thought later, not just answer and move on.

**Emotional balance:** `EmotionCompass` runs *first*, computing a live affect vector every
message. Because of the same-turn event bus, a `distress.detected` event it emits is
visible to `ChallengeCalibrator` (eases difficulty) and `HumorDelightGuide` (suppresses
ill-timed jokes) *within that same turn* — the system can soften in real time, not just on
the next message. `BeliefCoach` operates on a slower, cross-session clock: it's the sole
writer of the psychological profile, tracking the gap between a child's stated confidence
and their actual measured mastery, and coaching toward growth-mindset framing when the two
diverge.

**Motivation:** honestly the weakest link today. Nothing in the live 15 tracks *sustained*
drive — `ChallengeCalibrator`'s productive-struggle calibration (keeping difficulty in a
motivating zone) and `HumorDelightGuide`'s delight tracking are adjacent, real
contributors, but neither is a direct motivation signal. This is a genuine design gap
(see dimension #9 above), not a data-volume problem — it needs a new metric, not more
usage.

## 5. Honest caveat on all of the above

Most of these agents self-gate below a minimum sample count (`sample_count < 3–10`
depending on the agent) and return an empty string until then, by design — so today, for
almost any real child, the actual populated depth is thin. The architecture is real and
correctly wired; the *content* is still waiting on real usage volume to fill in. This
report describes what the system is built to do, not yet what it has done for any
specific child.
