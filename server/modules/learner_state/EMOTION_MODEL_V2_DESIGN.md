# Emotion Model v2 — continuous affect, not discrete relabeling

## The problem with the current system

Today emotion is a single categorical label re-classified from scratch on every
turn, with no memory of the previous state:

```
learner/signals.py / modules/learner_state/signals.py   → regex heuristic picks ONE of
                                                            {frustrated, distressed, anxious,
                                                             confused, curious, excited,
                                                             disengaged, neutral}
pipeline/evaluator.py / modules/tutor_runtime/evaluator.py → LLM confirms/overrides that ONE label
modules/learner_state/agents/sessional_emotion.py          → SET last_emotion = $2   (overwrite, no blend)
modules/learner_state/agents/emotion_compass.py             → maps the ONE label onto a 5-way
                                                                probability vector (lookup table,
                                                                not a model of transition)
modules/lens/affect.py                                       → "trajectory" = mode/frequency count
                                                                over the label history (a histogram,
                                                                not a dynamical trajectory)
```

Three structural problems follow directly from this:

1. **No continuity.** `last_emotion` is overwritten every turn. A child moving from
   confusion → productive struggle → breakthrough looks identical, event-by-event,
   to a child oscillating between confused and excited at random — the system
   cannot tell "on a trajectory toward X" from "just landed on X".
2. **No intensity.** "Frustrated" is frustrated whether it's a flicker of annoyance
   or a full shutdown. Discrete labels collapse magnitude, so there's no signal for
   *how urgently* to intervene, only *whether* a label crossed a threshold.
3. **Reactive, not predictive.** Because there's no velocity/slope, the system can
   only respond after a negative label has already fired — it can't catch the
   drift *before* curiosity tips into frustration.

## Theoretical foundation

**Core affect / circumplex model (Russell 1980; Russell & Barrett 1999).**
The claim that discrete emotion words are the wrong primitive is not just an
intuition — it's the mainstream view in affective science. Core affect theory
holds that the primitive, continuously-varying substrate is a point in a low
dimensional space — **valence** (unpleasant ↔ pleasant) and **arousal/intensity**
(deactivated ↔ activated) — and that discrete labels ("frustrated," "curious")
are coarse regions carved out of that space post-hoc for communication, not the
underlying state itself. This is exactly the shift the user asked for: valence +
intensity as the base representation, with named emotions becoming a read-out /
quadrant classification for humans (teacher reports, prompts) rather than the
system of record.

Practical quadrant mapping (matches the vocabulary already in this codebase, so
existing prompts/labels keep working as a projection of the new state):

| | high intensity | low intensity |
|---|---|---|
| **+valence** | curious / excited / flow | content / satisfied |
| **−valence** | frustrated / anxious | bored / disengaged |

`confused` sits near the origin, slightly negative valence, moderate intensity —
the "unstable" region that D'Mello & Graesser's data (below) shows resolves
quickly in one of two directions.

**Transition dynamics — D'Mello & Graesser, "Dynamics of Affective States during
Complex Learning," *Learning and Instruction* 22 (2012): 145–157.** This is the
directly relevant prior art: they instrumented real tutoring sessions and modeled
*which* affect transitions actually occur, not just which states occur. Their
finding, confirmed via time-series/Markov analysis: affect during learning moves
in a small number of characteristic oscillations, not a fully-connected graph of
equally likely jumps —

- **confusion ⇄ engagement/flow** — confusion triggered by a genuine impasse
  resolves into flow when the child works through it (their "cognitive
  disequilibrium" account, tracking Csikszentmihalyi/Piaget)
- **confusion ⇄ frustration** — the same impasse, unresolved, escalates instead
- **boredom ⇄ frustration** — the two negative "sinks" feed each other rather
  than transitioning to positive states directly

The practical implication: a state-transition model should have a **transition
graph with different resistances per edge**, not a single decay-to-neutral rule.
Confusion is the fork in the road; which way it resolves is the one thing the
tutor can actually influence in real time. This is also the empirical basis for
"one thought leads to another" — the child doesn't teleport from curious to
bored, they pass *through* confusion or frustration to get there, which gives an
intervention a window to act before the negative state consolidates.

**Why transitions happen — Pekrun's Control-Value Theory of Achievement Emotions.**
Circumplex position + D'Mello's transition graph describe *what* is happening;
control-value theory explains *why*, via two appraisals: perceived **control**
("can I do this?") and perceived **value** ("does it matter to me?"). High
control + high value → enjoyment/curiosity. Low control + high value →
anxiety/frustration. Low value (regardless of control) → boredom. This gives the
appraisal engine concrete inputs to compute from turn-level signals that already
exist in this codebase (`eval_result`, hint usage, consecutive struggles,
elapsed/lag time): control ≈ f(recent correctness, hint reliance, time-on-task
vs. expected), value ≈ f(topic-of-interest match, novelty, chosen-vs-assigned).

**Emotional contagion — Hatfield, Cacioppo & Rapson (1993).** For peer
interaction: contagion runs via mimicry → physiological feedback → convergence,
and its strength is gated by rapport/relationship closeness — i.e. exactly the
"assuming they trust each other" condition the user named. This motivates
modeling peer influence as a **trust-weighted pull toward the interlocutor's
(valence, intensity)**, not a copy of their state.

## Proposed representation

```python
@dataclass
class EmotionState:
    valence: float     # -1.0 (very unpleasant) .. +1.0 (very pleasant)
    intensity: float    #  0.0 (flat/deactivated) ..  1.0 (highly activated)
    # velocity is derived, not stored — computed from the trailing window
```

Discrete labels (`frustrated`, `curious`, ...) become a **projection** of this
state (quadrant + distance-from-origin lookup), computed on read, so every
existing consumer (`emotion_compass`, `evaluator` prompt vocabulary, teacher
narratives in `lens/affect.py`) keeps working unchanged during migration.

## Update rule ("one thought leads to another")

Each turn produces an **appraisal impulse** `(Δv, Δa)` from turn-level signals
(control/value features above, reusing the existing regex+LLM heuristics as the
feature extractor rather than the label picker). The state does **not** jump to
that impulse — it's integrated, spring-damper style, against the *previous*
state, biased by the D'Mello transition graph (an edge with low prior likelihood,
e.g. bored→excited in one step, gets heavily damped; an edge that's a known
oscillation, e.g. confused→frustrated or confused→flow, integrates at full
strength):

```
valence_t   = valence_(t-1)   + k_v * edge_weight * (Δv_appraisal - valence_(t-1))   + noise
intensity_t = intensity_(t-1) + k_a * edge_weight * (Δa_appraisal - intensity_(t-1)) + noise
```

`edge_weight` is looked up from the current discrete-projection region (the
"where am I now" side of the D'Mello graph) to the appraisal's target region.
This is deliberately simple (no ML training required to start) — it's a
calibratable prior, not a black box, and every constant is a knob a teacher/PM
can reason about.

## Intervention policy ("switch gears")

The policy watches the **trajectory**, not the point value — specifically the
recent slope of valence and intensity over the last few turns — so it can act
while a shift is still in motion:

| valence slope | intensity slope | read | gear shift |
|---|---|---|---|
| falling fast | rising | frustration ramp | simplify / offer a hint / encouragement, before full frustration lands |
| flat-low | falling | boredom drift | inject novelty, raise stakes, humor |
| rising | rising | curiosity/flow building | lean in, don't interrupt, go deeper |
| high | falling | satisfied wind-down | consolidate, praise, close the loop |
| near origin, was negative | any | recovering from confusion | reinforce whichever resolution just happened (this is the fork D'Mello identifies — treat it as a moment to cement flow, not just relief) |

This is strictly more information than the current system has (which only sees
`last_emotion` as a point value with no history), and it's cheap to compute —
a fixed-size rolling window of the last N states.

## Peer interaction ("how these models can talk to each other")

Each simulated student = existing persona (`tests/personas.py`) + an
`EmotionState` + a **trust** scalar toward each interlocutor (0 = stranger, 1 =
close friend). After each exchange between two simulated students:

1. Each appraises the exchange content itself (did the peer's message help,
   confuse, encourage, dismiss?) → own appraisal impulse, integrated as above.
2. Each is additionally pulled toward the *other's* (valence, intensity),
   scaled by `trust` (Hatfield's convergence mechanism) — modeled as a second,
   smaller-weight impulse rather than a copy.

This gives a directly testable prediction: pairs with high trust should show
valence convergence over a conversation; low-trust pairs should stay
independent even when discussing the same content. That's the proxy for real
peer interaction the user described, and it's checkable by eye in the
simulation output before any of this touches production.

## What's built now vs. next

**Built in this pass** (additive, no schema/DB changes, no production wiring):

- `emotion_engine.py` — `EmotionState`, appraisal-from-heuristics, the
  transition-graph-weighted update rule, discrete-label projection, and the
  gear-shift policy. Pure Python, no dependencies, unit-testable in isolation.
- `tests/simulate_peer_emotion.py` — runs pairs of existing personas through a
  scripted or alternating exchange, prints the valence/intensity trajectory,
  gear-shift events, and trust-scaled convergence, entirely offline (no
  server/DB/LLM required, so it's runnable right now).

**Deliberately not done yet** (needs a decision + touches production behavior):

- Swapping `emotion_compass.py` / `sessional_emotion.py` to store
  `EmotionState` instead of overwriting `last_emotion` (schema change:
  `learner_state.affect_state` would need `valence`/`intensity`/`updated_at`
  columns and a migration).
- Changing the `evaluator.py` LLM prompt from "pick one label" to "estimate
  control/value appraisal features" (changes model cost/latency profile,
  worth A/B'ing before committing).
- Wiring the gear-shift policy's output into the response-generation prompt
  (`kernel/orchestrator.py`) so the tutor actually acts on it.

Recommend validating the engine + peer-simulation behavior first, then doing
the production integration as a second, separately-reviewable change.
