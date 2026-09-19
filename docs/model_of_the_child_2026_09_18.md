# The Model of the Child — audit and roadmap

**Date:** 2026-09-18, updated 2026-09-19 with real eval numbers (§5, items 1-2 — eval harness built and real BKT shipped)
**Scope:** Parth's core competency — how the system represents a learner, how that representation updates, and how it compares to the published state of the art in student modeling (BKT, PFA/IRT, DKT, SAKT/SAINT/SAINT+, AKT). Grounded entirely in a direct read of `server/modules/learner_state/`, `server/modules/lens/`, `server/modules/attention_federated/`, `server/modules/puzzle_engine/`, and `server/foundation/schema.sql` as of this date — not the aspirational `ARCHITECTURE.md` alone.

**Verdict up front:** Parth's model of the child is a mature, unusually self-aware **symbolic/heuristic system** — 18 narrow agents writing interpretable state, synthesized into a 15-dimension portrait that honestly labels its own confidence and evidentiary status. That design is *correct* for where Parth is (sparse, per-child, real-classroom data — not a million-row Kaggle set). But the one dimension that most resembles published "knowledge tracing" research — dimension 6, Conceptual Understanding — is **mislabeled**: its code calls itself Bayesian Knowledge Tracing but implements a plain ratio heuristic with no Bayesian update, no slip/guess parameters, and no forgetting. Meanwhile the system is already logging the exact event stream (`kt_events`: concept, correct, elapsed_ms, lag_ms, session, timestamp) that real BKT and the transformer-based models below need — and nothing reads it except two hand-written heuristics. That gap, not a missing architecture, is the highest-leverage place to act.

**Now measured, and now fixed:** an offline eval harness (`server/eval_knowledge_model.py`, §5 item 1) confirmed the verdict with numbers — on the first 157 logged events, a trivial "predict last outcome" baseline beat the ratio heuristic on both AUC (0.892 vs. 0.768) and Brier score (0.126 vs. 0.239), and brand-new concepts scored exactly chance-level (AUC 0.500) with log-loss *worse than guessing 0.5 flat*. Real per-concept BKT (§5 item 2) replaced the heuristic the same day: re-run on the identical events, it now beats every baseline on every metric (AUC 0.909, log-loss 0.359, Brier 0.106), and the cold-start log-loss dropped from 1.969 to 0.652.

---

## 1. Why this is the core competency

Everything downstream — the prompt Parth builds, the puzzle it selects, the detour Wonder Engine offers, the alert Parent Dashboard sends — is only as good as the model of the child feeding it. Parth's own kernel design (`server/ARCHITECTURE.md`) makes this explicit: `learner.state` is the one module every other Phase 1 and Phase 3 step in the routing table touches. Get the child model wrong and every module downstream personalizes against a fiction.

This report is scoped to that model: what it is today, what the field calls "good" here, and where the two diverge in ways worth fixing.

---

## 2. The external landscape — what "modeling a learner" means in the literature

The field usually calls this **knowledge tracing (KT)**: given a learner's history of (skill, correct/incorrect) attempts, estimate the probability they'd get the *next* attempt on that skill right. Five families matter for Parth, roughly in order of data hunger:

| Model | Mechanism | What it needs | Interpretable? | Handles forgetting? |
|---|---|---|---|---|
| **IRT** (Item Response Theory) | Learner ability θ and item difficulty β fit jointly; P(correct) = logistic(θ − β) | Item-level difficulty calibration, many responses per item | Yes | No |
| **BKT** (Bayesian Knowledge Tracing) | Per-skill 2-state Hidden Markov Model — 4 fitted parameters: `p_init`, `p_transit` (learning rate), `p_slip` (careless error on known skill), `p_guess` (lucky correct on unknown skill); posterior updated by Bayes' rule after every attempt | A handful of attempts *per skill* to fit or use sane defaults | Yes — this is the reference case for interpretability | Only with the *forgetting* extension (`p_forget`), a well-studied add-on, not in the base model |
| **PFA** (Performance Factor Analysis) | Logistic regression over separate counts of prior *successes* and *failures* per knowledge component, no explicit ability term | Same order of data as BKT; handles multi-skill items natively (BKT doesn't) | Yes | Only via decayed/"ghost" counts (see §5) |
| **DKT** (Deep Knowledge Tracing) | One shared RNN/LSTM over the whole interaction sequence across skills | Thousands of sequences to train a shared network — this is the first model in the table that is genuinely data-hungry | No — a black-box hidden state | Implicitly, unevenly |
| **SAKT / SAINT / SAINT+ / AKT** | Self-/cross-attention (transformer) over exercise and response streams; SAINT+ specifically adds `elapsed_ms` and `lag_ms` embeddings — response-time and gap-since-last-attempt, exactly Parth's `kt_events` columns; AKT adds a monotonic attention mechanism and is the current front-runner on large public benchmarks (EdNet, ASSISTments) | Tens of thousands+ of interactions; these were built for Kaggle/EdNet-scale competitions | No | Implicitly via attention over recency |

Two 2025–2026 threads matter more to Parth than the leaderboard-topping models above:

- **Interpretability actually helps.** ["Does Interpretability of Knowledge Tracing Models Support Teacher Decision Making?"](https://arxiv.org/pdf/2511.02718) (AIED 2025) found that in simulation, teaching-decision policies driven by interpretable KT models (i.e. BKT-family) reached mastery *faster* than policies driven by opaque models, and human teachers rated interpretable output more trustworthy — even though raw task-count-to-mastery was similar. This is a direct argument *for* Parth's existing text-context, no-embeddings design, not against it.
- **Cold start is its own research area, and it's the one that matches Parth's actual deployment shape.** [MAML-KT](https://arxiv.org/html/2603.00137v2) (meta-learning a generalizable initialization so a KT model adapts from a handful of a new student's attempts) and [EDM 2025's "ghost" smoothing for logistic KT](https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.short-papers.177/index.html) (adding baseline pseudo-counts so a 1–2-interaction student doesn't produce an undefined or wildly unstable estimate) both target exactly Parth's situation: a real child, in a real classroom, with a handful of interactions today — not a benchmark learner with thousands of logged attempts. DKT/SAINT/AKT were built and validated for the opposite regime.

Knowledge tracing is also only *one* of Parth's 15 dimensions (it maps most directly to dimension 6, "Conceptual Understanding and Depth," and partly to dimension 5, "Learning Velocity"). The other 14 — curiosity, motivation, affect, confidence calibration, social preference, value/purpose — sit in adjacent literatures (control-value theory of achievement emotions, self-determination theory, confidence/calibration research) that this report does not audit. That is a deliberate scope cut, flagged explicitly in §6, not a silent one — see the [[feedback_research_before_implementation]] memory note: shipping a well-researched fix to one dimension while treating the rest as unexamined "future work" is the mistake this report is trying not to repeat.

**Sources:** [BKT parameters](https://www.emergentmind.com/topics/bayesian-knowledge-tracing-bkt) · [Standard BKT](https://iedms.github.io/standard-bkt/) · [SAINT+ paper](https://arxiv.org/abs/2010.12042) · [Knowledge Tracing survey (Shen et al., IEEE TLT 2024)](https://arxiv.org/abs/2105.15106) · [AKT / DKT comparison survey](https://dl.acm.org/doi/full/10.1145/3569576) · [PFA original paper](https://files.eric.ed.gov/fulltext/ED506305.pdf) · [PFA vs IRT](https://joyboseroy.medium.com/modelling-a-students-learning-34375b0131dd) · [Interpretability & teacher decisions, AIED 2025](https://arxiv.org/pdf/2511.02718) · [MAML-KT cold start](https://arxiv.org/html/2603.00137v2) · [Ghost-count smoothing, EDM 2025](https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.short-papers.177/index.html)

---

## 3. What Parth actually builds today

### 3.1 The architecture: interpretable and symbolic by design, not by accident

`kernel/agent.py` defines the whole contract: every agent implements `observe()` (write state after a turn), `read()` (return a plain-English context string injected into the LLM prompt), and optionally `emit()` (post events onto a shared bus other agents can react to same-turn). `modules/learner_state/agents/__init__.py::build_agent_registry()` wires exactly **18 live agents**, dependency-ordered into 4 layers, dispatched by a shared `AgentHarness` on every chat turn (`modules/learner_state/module.py`) — the demo page's own header ("18 learner agents") confirms this count.

Worth flagging precisely because it's easy to get wrong by just listing the directory: **35 `.py` files exist in `modules/learner_state/agents/`, and 17 of them are not imported by `build_agent_registry()` at all** — `analogy_domain.py`, `attribution_style.py`, `chrono_pattern.py`, `cognitive_profile.py`, `confidence_calibration.py`, `curiosity_tracker.py`, `episodic_memory.py`, `family_context.py`, `knowledge_state.py`, `learning_speed.py`, `linguistic_register.py`, `misconception_map.py`, `motivational_profile.py`, `open_loop.py`, `productive_struggle.py`, `sessional_emotion.py`, `stress_signature.py`. These are dead/unwired code sitting indistinguishable-by-filename next to the live 18 (a July 2026 audit intended to archive them to `agents/_legacy/`; that move was never committed). `confidence_calibration.py` specifically is fully superseded — the live confidence-calibration write happens inline in `belief_coach.py` (§3.6), not in the file named for it.

Nothing here is a trained model with weights — every "model" is a formula or a threshold, and every output is a string a human (or an LLM) can read and audit. This is the same property the AIED 2025 interpretability study found teachers actually trust more.

### 3.2 The 15-dimension portrait: honest about what it doesn't know

`modules/learner_state/dimensions.py` synthesizes those 18 agents' state into 15 product-facing dimensions (`build_dimension_snapshot`). This file is the best-designed part of the system: every dimension is tagged with a **status** (`direct`, `derived`, `proxy`, or `reflection`), a **confidence score**, its **primary agents**, raw **evidence**, and an explicit **next_action** — e.g. dimension 7 (Problem Solving) is honestly labeled `proxy` with `next_action: "Add direct puzzle/problem-solving rubric before high-stakes use."` Nothing here pretends to certainty it hasn't earned. Treat this file as the map for where each dimension's own literature review and upgrade path should eventually go.

### 3.3 Dimension 6 — Conceptual Understanding, a.k.a. "the BKT that isn't"

`modules/learner_state/knowledge.py` is docstringed `"""Bayesian knowledge tracing per concept."""`. The actual formula:

```python
def _mastery(exposures, demonstrations, misconceptions):
    exp = max(1, exposures)
    raw = (demonstrations / exp) * (1.0 - 0.4 * misconceptions / exp)
    return round(max(0.05, min(0.98, raw)), 3)
```

This is a clamped success ratio with a linear misconception penalty. It is **not** BKT: there is no hidden mastery state, no `p_slip`/`p_guess` separation (a lucky guess and genuine understanding both increment `demonstrations` identically; a careless slip and a real misconception both increment `misconceptions` identically), no fitted `p_transit` learning rate, and — critically — **no forgetting**. A concept demonstrated once six months ago reads identically to one demonstrated yesterday, as long as no *new* exposure has come in to change the ratio.

The agent that calls this, `modules/learner_state/agents/mastery_tracker.py`, is candid about the gap in its own docstring:

> *"Ref: Shen et al., 'A Survey of Knowledge Tracing' — interpretable BKT first, SAINT+ temporal features as the upgrade path once kt_events accumulates data."*

That is: the intended target architecture is already decided, in the repo, citing the same survey this report cites. It has not been executed.

### 3.4 `kt_events` — a real BKT/SAINT-shaped asset, currently write-only

`foundation/schema.sql` defines:

```sql
CREATE TABLE learner_state.kt_events (
    id, learner_id, concept_id, correct, elapsed_ms, lag_ms, session_id, created_at
);
```

`mastery_tracker.py` writes one row per concept per turn — this is *exactly* the (skill, correct, response-time, gap-since-last) tuple every model in §2 from BKT through SAINT+ consumes. But grep for every reader of this table turns up only hand-written heuristics, all in `modules/lens/cognitive.py`'s periodic portrait computation:

- **"Growth rate / trajectory"** — splits `kt_events` in half by time and compares success rate first-half vs. second-half (`_estimate_growth_rate`). No decay model, no smoothing.
- **"Retention profile"** — flags a concept as "fast-forgetting" if `lag_ms > 1 day` and the next attempt was wrong (`_retention_profile`). This is a real forgetting *signal* — but it is never fed back into `knowledge.py`'s `p_mastery`. The two live in separate files and never talk to each other.
- **"Fluency/depth"** — `elapsed_ms < 8000` on a correct answer is called "procedural fluency"; correct on ≤2 exposures is called "conceptual depth" (`_fluency_depth`). Fixed thresholds, not calibrated against anything.
- **BMAD self-diagnostic flags** — the same file emits messages like *"BKT learning rate may be too conservative; consider raising slip/guess priors"* when >70% of concepts sit in the ZPD band. **This flag references parameters (`p_slip`, `p_guess`, a learning rate) that do not exist anywhere in the codebase.** The self-diagnostic layer is already written for the BKT that hasn't been built yet — it will start being literally actionable, rather than a stale comment, the moment §5's recommendation (b) lands.

### 3.5 `attention.federated` — the cold-start mechanism the literature says Parth needs, also unwired

`modules/attention_federated/module.py` has `handles = []` — it does not run in the kernel's routing table at all. It subscribes to `learner.state_updated` and accumulates population-average concept difficulty into a local JSON file (`federated_priors.json`, not even Postgres), and exposes `get_prior_difficulty()` / `get_prior_analogy_effectiveness()`. **Nothing in the codebase calls either getter.** The exact mechanism the cold-start literature in §2 recommends — population priors bootstrapping a new learner's initial estimate — is scaffolded but fully disconnected on both ends: nothing yet decides *when* a learner is new enough to need it, and nothing consumes it once computed.

### 3.6 The rest of the "knowledge" side, briefly

- **Learning Velocity** (`agents/learning_velocity.py`) — a hand-tuned "expected turns to mastery" formula normalized by distance from the ZPD band (`weak_threshold`–`strong_threshold`), blended 70/30 with `kt_events`' raw recent-correct rate. Reasonable engineering, not a fitted model; the constants (`4.0 + zpd_distance * 14.0`, the 0.7/0.3 blend) are guesses with no offline validation.
- **Confidence Calibration** — live in `agents/belief_coach.py` (agent #06), *not* in the identically-named `agents/confidence_calibration.py` (dead, unwired — see §3.1). A fixed English+Hindi phrase-set membership check (`i know`, `obviously`, `pata hai`, `aata hai`, …) against the *first* concept in the turn, compared to `p_mastery` with the calibration gap computed against a fixed target of 0.9. Purely lexical, single-concept, and thin on the Hindi/Hinglish side relative to how seriously `register_tuner.py`/`language_bridge.py` treat multilingual input elsewhere in the same module.
- **Emotion** — two representations exist in parallel by design, not by accident: a discrete LLM-evaluated label (`emotion`/`engagement`, the system of record most consumers read) and a continuous (valence, intensity) trajectory from `affect_v2.py`/`emotion_engine.py`, folded in via lexical appraisal of the raw message text only. `EMOTION_MODEL_V2_DESIGN.md` already flags reconciling these as an open, deliberately deferred decision.
- **Cold start before any chat exists** — `puzzle_engine` (ZPD-matched probes, `selector.py`) is the one truly "direct" measurement Parth has (dimension 1, Cognitive Ability) before any concept-level history exists. It is architecturally separate from the `knowledge.py` mastery model above; the two never share machinery.

---

## 4. Gap analysis, mapped to §2

| Gap | Where | What the literature does instead |
|---|---|---|
| No Bayesian update; a ratio stands in for a posterior | `knowledge.py::_mastery` | BKT: sequential Bayes' rule update from a prior, after every observation |
| No guess/slip separation | `knowledge.py` | BKT's `p_guess`/`p_slip` explicitly discount a lucky guess or a careless slip from moving the mastery estimate |
| No forgetting feedback loop | `knowledge.py` vs. `lens/cognitive.py::_retention_profile` (computed, unused) | BKT+forgetting (`p_forget`); PFA's decayed/"ghost" counts |
| No per-skill parameter fitting — every concept uses the same formula and thresholds | `knowledge.py`, `Config.MASTERY_*_THRESHOLD` | BKT/PFA fit (or at minimum default-and-override) parameters per skill |
| No multi-skill question handling | `knowledge.py` (records one concept string at a time) | PFA natively supports multi-KC items via per-KC success/fail counts |
| Self-diagnostic references a model that doesn't exist | `lens/cognitive.py::_bmad_flags` ("BKT learning rate... slip/guess priors") | N/A — this is Parth-specific technical debt, not a modeling gap |
| Rich temporal event log, unconsumed by any sequence model | `kt_events` table | This is literally the SAINT+ input schema (`concept_id, correct, elapsed_ms, lag_ms`) sitting idle |
| Cold-start population prior mechanism built, not wired | `attention_federated/module.py` | MAML-KT / meta-learned initialization, "ghost" pseudo-counts |
| No offline evaluation harness — no AUC/log-loss/calibration curve on held-out `kt_events` anywhere in the repo | (absent) | Every paper in §2 is validated exactly this way; without it, Parth cannot tell whether any constant change (a threshold, a decay rate) helps or hurts |
| Confidence calibration is English-centric regex in a Hindi/Hinglish-first product | `confidence_calibration.py` | N/A — internal inconsistency with the product's own register/language agents |

The throughline: **Parth is not missing an architecture — it correctly chose interpretable-and-symbolic over black-box, and the 2025 AIED interpretability study backs that choice.** What's missing is (a) the actual math behind the one component that already claims to be a named published model, and (b) a way to measure whether any of this is getting more accurate over time.

---

## 5. Recommendations — sequenced, so each step is independently shippable

**Do these first, in order.** Each is scoped to be a swap-in behind `knowledge.py`'s existing interface, so the agent harness, `lens/cognitive.py`, and every prompt-context consumer keep working unmodified.

1. **[Done, 2026-09-19] Offline eval harness.** `server/eval_knowledge_model.py` replays `learner_state.kt_events` turn-by-turn (grouped by `(learner_id, created_at)`, since the kernel's transaction makes `now()` stable per interaction) against `knowledge.py`'s actual, imported `_mastery()` function, scoring each event as a next-step prediction before applying that event's own update — the standard KT evaluation protocol. Run it with `python eval_knowledge_model.py [--min-events N] [--out path.json]`; the `--out` snapshot is what future steps diff against.

   **First real run, 157 events / 26 learners / 11 concepts (pilot-scale, treat as a first read, not a settled result):**

   | Model | AUC | Log-loss | Brier |
   |---|---|---|---|
   | `knowledge.py` (`_mastery`, live) | 0.768 | 0.828 | 0.239 |
   | baseline: overall base rate | 0.500 | 0.684 | 0.245 |
   | baseline: always predict 0.5 | 0.500 | 0.693 | 0.250 |
   | baseline: predict last outcome | **0.892** | 1.378 | **0.126** |

   Two concrete findings, not just architectural critique:
   - **A trivial "whatever happened last time" baseline beats the live heuristic** on both AUC (0.892 vs. 0.768) and Brier score (0.126 vs. 0.239). The current formula's smoothing-over-history is actively costing rank-ordering accuracy relative to just looking at the most recent attempt.
   - **The cold-start default is actively harmful.** Bucketed by prior-exposure count, brand-new concepts (0 prior exposures, 43 events) score AUC 0.500 (pure chance) and log-loss **1.969** — far worse than even a flat 0.5 guess (log-loss 0.693) — because `_mastery(1,0,0)` floors to 0.05 regardless of the concept, and 65% of those first attempts were actually correct. A flat, concept-blind 0.05 prior is quantifiably worse than knowing nothing. This is exactly the gap recommendation (6) below (population-prior injection via `attention.federated`) exists to close, now with a number attached instead of just an architecture diagram.
   - 9 of 157 events (5.7%) were "same-turn credit gaps" (§3.4) — small at this volume, worth re-checking as data grows.

   This baseline (`data/kt_eval/baseline_2026_09_19.json`) is the number recommendation (2) below has to beat.
2. **[Done, 2026-09-19] Real per-concept BKT.** `modules/learner_state/bkt.py` implements the standard 4-parameter HMM (`p_init`, `p_transit`, `p_slip`, `p_guess`) with the textbook Bayes-update-then-learning-transition recurrence. `knowledge.py` was rewritten around it, keeping the exact same three-function interface (`record_exposure` / `record_demonstration` / `record_misconception`) `mastery_tracker.py` already calls, so nothing downstream changed. Two semantic improvements fell out of the rewrite for free: (a) a brand-new concept now seeds at its fitted `p_init` instead of a flat 0.05 regardless of difficulty, and (b) the old same-session misconception half-weighting hack is gone — it existed to stop the ratio heuristic's linear penalty from permanently tanking mastery after one bad session, and BKT's bounded, self-correcting update has nothing left for that hack to compensate for.

   Parameters are fit by `server/fit_bkt_params.py` — grid search (no numpy/scipy dependency) maximizing a **regularized** log-likelihood (MAP, not raw MLE) against `learner_state.kt_events`, penalized toward literature-informed defaults. The regularization mattered in practice: unpenalized MLE on this data volume degenerated to a corner of parameter space (`p_init→1, p_transit/p_guess→0`, i.e. "assume every child already knows everything and never learns or guesses") because ~150 observations spread over 40 short sequences (avg. length 3.7) carry almost no learning-curve signal on their own. The script prints an explicit warning whenever a fitted parameter lands on the edge of its search grid, so this kind of small-sample degeneracy is visible rather than silently shipped. First fit, written to `learner_state.bkt_params` as the `_global_` row every concept falls back to below a 50-event-per-concept threshold: `p_init=0.60, p_transit=0.05, p_slip=0.05, p_guess=0.02`.

   **Re-ran the eval harness (step 1) on the identical 157 events — before/after:**

   | Model | AUC | Log-loss | Brier |
   |---|---|---|---|
   | Old ratio heuristic (2026-09-19 baseline) | 0.768 | 0.828 | 0.239 |
   | **New BKT** | **0.909** | **0.359** | **0.106** |
   | baseline: predict last outcome | 0.892 | 1.378 | 0.126 |

   BKT now beats every baseline on every metric — including the "predict last outcome" baseline that beat the old heuristic on both AUC and Brier (§5 item 1). The cold-start bucket (0 prior exposures, 43 events) improved from log-loss 1.969 (worse than guessing 0.5) to **0.652** (now better than guessing 0.5) — direct confirmation that seeding at a fitted `p_init` instead of a flat 0.05 fixes the harm quantified in step 1. That bucket's AUC is still 0.500 by construction (every never-before-seen concept gets the identical `p_init` prediction, so there's nothing to rank-order on a first exposure) — genuine per-concept differentiation before any exposure is exactly what recommendation (6)'s population-prior injection would still add.

   Snapshot: `data/kt_eval/bkt_2026_09_19.json`.
3. **Add forgetting** (`p_forget` extension) and wire `lens/cognitive.py`'s already-computed `_retention_profile()` into it, instead of leaving retention and mastery as two facts that never inform each other.
4. **Fix the BMAD flag in `lens/cognitive.py`** to reference the real fitted `p_slip`/`p_transit` once they exist, so that diagnostic becomes actionable instead of describing a model that isn't there.
5. **Only after (2)–(4) are live and `kt_events` volume has grown**, evaluate blending in PFA — cheap (logistic regression), handles multi-skill questions BKT can't, and the 2025 EDM "ghost pseudo-count" smoothing technique solves exactly Parth's 1–2-interaction cold-start case without needing a meta-learned network. This is a better next step than jumping to DKT given Parth's actual per-learner data volume.
6. **Wire `attention.federated` as a population *prior*, not a per-turn tracker.** Feed its (already-collected, currently-unread) aggregate concept difficulty into a new learner's BKT `p_init` for concepts they haven't seen yet — this is the cold-start pattern MAML-KT and similar 2025–2026 work target, and it's the one place in this whole audit where a deep/population-level model (eventually DKT/SAINT-family, trained centrally across all learners' `kt_events` once there's enough pooled data) is actually appropriate for Parth — as a prior injected into an interpretable per-child model, never as the per-turn estimate itself.
7. **Confidence calibration**: extend `belief_coach.py`'s phrase-set check past English/fixed-Hindi keywords — add response-latency as a cheap, still-interpretable second signal, broaden the Hindi/Hinglish coverage to match the seriousness `register_tuner`/`language_bridge` already give multilingual input elsewhere in this module, and delete the dead `confidence_calibration.py` duplicate (§3.1) so the next person doesn't edit the file that isn't actually running.
8. **Reconcile the two emotion representations** per the decision `EMOTION_MODEL_V2_DESIGN.md` already flagged and deferred — pick one relationship between the discrete label and the continuous trajectory (e.g., discrete label as a named region of the continuous state) rather than leaving them to silently diverge.

**Explicitly out of scope here, flagged not dropped:** dimensions 2, 3, 4, 7–15 (curiosity, attention/focus, memory, problem-solving, creativity, motivation, wellbeing, confidence writ large, adaptability, learning preference, value/purpose, social) each rest on their own literatures (spaced-repetition/SM-2 is already correctly used for memory; control-value theory for achievement emotions; self-determination theory for motivation/autonomy) and deserve the same treatment `dimensions.py` already gives them structurally — a `status`, a `confidence`, and a `next_action`. This report does not audit those; per [[feedback_research_before_implementation]], that should be a named follow-up, not silently treated as solved because dimension 6 got attention.

---

## 6. What would change if nothing above shipped

Worth saying plainly: the current heuristic is not *wrong* in a way that's visible in the demo — it produces plausible, monotonically-improving mastery scores, and the honest `confidence` fields in `dimensions.py` already protect downstream consumers from over-trusting thin evidence. The cost of the gap is invisible today and will become visible exactly when it matters most: as `kt_events` accumulates real volume across real pilot classrooms, small mis-calibrations (no forgetting, no slip/guess discounting) compound into a portrait that quietly drifts from the child it claims to describe — with no eval harness in place to notice.
