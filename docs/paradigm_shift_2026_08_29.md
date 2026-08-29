# Parth paradigm-shift review — 2026-08-29

Critical review of the 18-agent learner-state architecture, the curriculum
graph, and the tutoring prompt, prompted by a direct challenge: *students
need nonlinear examples to get motivated, they do not just have
misconceptions. Education is uncovering/discovering things, not stuffing
old knowledge for exams.* This document is the evidence for that critique,
what it does and doesn't change about the existing pilot, and what shipped
alongside it tonight (`server/modules/wonder_engine/`).

## 1. The critique, verified against the code

**Claim: Parth is structurally built to detect-and-correct along a linear
curriculum chain, not to generate discovery.** Verified true, with one
narrow exception.

- `curriculum_graph/graph.py::get_next_concept()` (the *only* function
  anywhere in the codebase that picks "what next") is a pure
  prerequisite-mastery gate: prerequisites need `p_mastery >= 0.45`,
  the current concept must be `< 0.70`, grade-bounded. One call site
  (`curriculum_graph/module.py`). Zero curiosity, interest, or tangent
  input anywhere in that decision.
- All 18 wired agents in `learner_state/agents/__init__.py` — including
  every one whose name suggests creative/curious/motivational work
  (`InquiryAlchemist`, `PatternCreationGuide`, `TransferWeaver`,
  `LearningVelocity`, `MotivationDrive`, `HumorDelightGuide`) — are
  detectors, scorers, or threshold-gates. None of them generate novel
  content. `PatternCreationGuide`'s "wonder questions" are picked from a
  fixed bank of 5-6 canned template strings (`open_loops.py`), gated by
  keyword match or "every 5th turn." `TransferWeaver` never invents a new
  cross-domain bridge — it only scores and retires analogies the tutor
  already used.
- `value_purpose.py` (the "Value and Purpose" of the 14 named child
  dimensions) is not wired into the agent registry at all. It's a
  standalone reflection-survey module nothing in the live tutoring loop
  calls.
- `curiosity.py` / `open_loops.py` produce advisory strings ("follow the
  dominant thread if there's a natural opportunity") appended to the
  prompt — nothing enforces them, and there is no code path that detects
  "the child is going off the curriculum DAG" and responds by *following*
  rather than *redirecting*.
- The base system prompt (`config.py::system_prompt()`, both grade
  branches) is explicitly convergent: "Break every complex topic into
  small, numbered steps," "End each response with ONE encouraging
  follow-up question to **check understanding**." Nothing in either
  branch authorizes a tangent, rewards an unconventional connection, or
  allows "I don't know, let's find out" as a valid answer.
- **The one real exception**: `puzzle_engine/cold_start.py` already
  contains genuinely nonlinear design — a cross-domain "Bridge puzzle"
  (`_BRIDGES` dict: mathematics→arts, physics→philosophy, ...) and a
  fully open-ended "tell me one thing that surprised you, there's no
  right answer" probe. This is real discovery-mode design, already
  written, already good — but it runs **only** during the first 5
  cold-start interactions per child, then is never used again. Every
  subsequent turn reverts to ZPD/mastery-driven puzzle selection and
  prerequisite-DAG curriculum content.

**Live confirmation, not just static reading**: I ran Parth's actual
grade<11 system prompt against `llama3.2:latest` and `gemma3:12b` (raw
Ollama calls, not through the app) with two prompt families — see
`/Volumes/Seagate/Parth/discovery_lab/model_eval/`:

- **Wonder** ("I just learned photosynthesis — is that all there is to
  know?"): both models responded with *more of the same curriculum
  content* — numbered steps, same-register concrete analogies (kite,
  samosa, jalebi, cricket ball). Zero instances of a genuinely
  cross-domain connection (art, economics, music, a paradox, a real
  historical accident) across 6 runs.
- **Misconception** ("heavier things fall faster... a rock obviously
  falls faster than a feather"): both models opened with correction
  framing — "That's close, but not exactly correct," "actually, in a
  vacuum..." — rather than validating the child's reasoning or proposing
  something to test first.

This means the bottleneck is **at least as much the prompt/architecture as
the model**: the same instructions produce the same convergent pattern
regardless of which 3-12B local model receives them. That doesn't rule out
a model effect on top of a fixed instruction — see §3 — but it means a
model swap alone would not have fixed this.

## 2. What shipped: Wonder Engine (additive, not a rewrite)

`server/modules/wonder_engine/` — a new, small, signal-gated module,
**additive** to the existing pipeline (curriculum_graph/RAG and MAG are
untouched; exam-relevant mastery tracking is untouched).

**The plan going in was to have an LLM generate new cross-domain
provocations from a hand-authored seed bank. That changed mid-build**:
`data/puzzles/v2/` already contains 300 puzzles across 10 spheres (10
mathematics, 15 physics, 20 philosophy_logic, ...), each with a `hook`,
a `challenge`, a `discover` insight, a `go_deeper` extension, and a
`silent_lesson` curriculum tie-back — authored, per its own header, as
"mathematics discovered, not delivered... the productive shock of
genuine mathematical surprise." This is *better* than anything an LLM
would generate live: real thinkers (Euclid, Socrates, ...), real
constructions, already curriculum-tagged. It was sitting completely
unused outside `puzzle_engine`'s separate cold-start onboarding flow
(`puzzle_engine/cold_start.py`, probes 4-5 — a genuine cross-domain
"Bridge puzzle" and an open-ended "no right answer" probe) — every turn
after the first five per child reverted to mastery-gated puzzle
selection and prerequisite-DAG curriculum content. **So the highest-
leverage move wasn't to author more content — it was to wire what
already existed into the standing chat loop.**

- **Trigger**: fires only when this session's dominant curiosity thread
  (`learner_state/curiosity.py`, unchanged, already tracks WHY/pushback/
  speculation/connection/return signals with decaying heat) crosses
  `Config.WONDER_HEAT_THRESHOLD` (default 0.55, curiosity.py's own "high"
  label) — not on every turn, and gated to at most once per
  `WONDER_MIN_MINUTES_BETWEEN_OFFERS` (default 20) per learner, so it
  never competes with routine exam-prep Q&A.
- **Real content, cross-domain by construction**: picks one puzzle from
  the sphere that `puzzle_engine/cold_start.py`'s existing `_BRIDGES` map
  bridges *to* from the child's current subject (physics → philosophy_logic,
  mathematics → arts_interdisciplinary, ...) — same cross-domain design as
  the cold-start Bridge puzzle, now available every session. The prompt
  instruction is explicit that this is optional ("only offer this if it
  fits naturally... never force it") and that Parth should guide the
  child toward the `discover` insight rather than stating it.
- **Misconception reframing**: a second, small prompt addition that
  activates on `learner.state`'s existing `misconception_hint` (already
  computed for curriculum_graph's remediation hint — reused, not
  reinvented), instructing Parth to validate the reasoning behind the
  wrong belief and propose something to test *before* correcting it.
- **Traceable, not just vibes**: when a puzzle is offered, the turn's
  `mag.memory` node is tagged with `concept_ids += ["_wonder:<puzzle_id>"]`,
  so MAG's existing causal-edge consolidation can, over time, surface
  whether a tangent connected back to a concept the child later mastered
  faster — instrumentation for "does discovery mode help or hurt exam
  readiness," not an assumed answer either way. Engagement detection
  (did the child actually take up the offer) is not implemented yet.

**Live-verified, not just unit-tested**: registered a test learner,
asked a real sequence of genuine "why" questions about gravity across
several turns, watched `learner_state.curiosity_sessions`' heat cross
0.55 exactly when expected, and confirmed `wonder_engine.offers` recorded
a real offer — `socrates_i` ("Define It Precisely" — Socratic elenchus,
family resemblance) — bridged from physics to philosophy_logic, exactly
as designed. Confirmed `on_erase` cleans it up.

## 3. Model choice: Mistral vs. Llama/Gemma

Ran Parth's actual grade<11 system prompt against `llama3.2:latest` and
`gemma3:12b` (raw Ollama calls, not through the app — isolates the base
model from tonight's architecture change) with WONDER and MISCONCEPTION
prompt families — harness and raw outputs at
`/Volumes/Seagate/Parth/discovery_lab/model_eval/` (external drive, per
tonight's brief; summary below is self-contained in this repo).

**Wonder** ("I just learned photosynthesis — is that all there is to
know?"): both models responded with *more of the same curriculum
content* — numbered steps, same-register concrete analogies (kite,
samosa, jalebi, cricket ball). Zero instances of a genuinely
cross-domain connection (art, economics, music, a paradox, a real
historical accident) across 6 runs.

**Misconception** ("heavier things fall faster... a rock obviously
falls faster than a feather"): both models opened with correction
framing — "That's close, but not exactly correct," "actually, in a
vacuum..." — rather than validating the child's reasoning or proposing
something to test first. gemma3:12b was marginally softer in tone but
made the identical structural move.

**Verdict: essentially indistinguishable for this purpose.** This is
strong evidence the bottleneck is the prompt/architecture, not model
choice between these two — the same instructions produced the same
convergent pattern regardless of which model received them. That's the
actual reason Wonder Engine is a prompt/data/architecture fix (§2)
rather than a model swap.

**Mistral — update, pull finished overnight**: ran the same 5 prompts.
**No clean winner, and one real accuracy concern.** On the WONDER
prompts — the actual cross-domain capability at stake — mistral did no
better, arguably worse: given "is that all there is to know about
photosynthesis?", it went *deeper into syllabus content* unprompted
(light-dependent/independent reactions, the Calvin cycle) rather than
anywhere near cross-domain. On MISCONCEPTION prompts it was genuinely
better on one: for "heavier things fall faster," it opened with *"You're
thinking like a scientist, my friend!"* (no correction-framing at all),
invoked Galileo's real Leaning Tower of Pisa experiment, and closed with
*"What do you think he found? Ponder this..."* — a real Socratic move,
the best single response of any model tonight. But on the seasons/tilt
prompt, mistral opened with *"You're absolutely right, my friend!"* —
validating the *factually wrong* claim (distance causes seasons) — then
described axial tilt without ever actually correcting the premise. A
child reading that could walk away still holding the wrong belief. That
is not a framing problem, it's a correctness problem, and it's a direct
cost of the same warmer, more-agreeable default register that made the
Galileo response good.

**Conclusion**: `Config.FAST_MODEL`/`DEFAULT_MODEL` were left unchanged.
Swapping to mistral trades a tone improvement on one axis for a real
accuracy risk on another, without improving the axis (cross-domain
wonder) that motivated pulling it in in the first place. Wonder Engine's
approach — reuse real, professionally-authored puzzle content instead of
hoping a different 3-12B local model invents a good cross-domain
connection on demand — remains the right lever. Full scoring and raw
mistral outputs: `mistral_comparison.md` at the path above.

## 4. What this does *not* claim to fix

This is one additive module, not a redesign of all 18 agents or the 14
named dimensions. `value_purpose.py` is still unwired. The curriculum DAG
is still purely mastery-gated (deliberately — exam performance still
matters, per the ask: "help the child clear all exams **as well as**
discover new things"). Whether Wonder Engine actually improves engagement
or retention is an empirical question this only *instruments* (via MAG),
not one it answers tonight.

One honest open question from the live test itself: in the one real
offer captured (`socrates_i`), the model's actual chat response didn't
visibly surface the puzzle — plausibly correct behavior ("only offer
this if it fits naturally... never force it" is followed literally), or
plausibly the instruction is too easy for a small local model to
deprioritize against the much more directive base system prompt above
it, the same failure mode §1 documents for curiosity threads and open
loops. Worth watching over more real turns before concluding the
"optional" framing is calibrated right, rather than just quietly never
firing in practice.
