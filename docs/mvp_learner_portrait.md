# MVP Learner Portrait

This project now separates the runtime learner harness from the product-facing
15-dimension portrait. The harness may have more or fewer agents over time; the
portrait remains the stable product contract.

## Dimension Contract

| # | Dimension | MVP source | Status |
|---|---|---|---|
| 1 | Cognitive Ability | Five cold-start puzzle probes before chat | Direct |
| 2 | Curiosity and Exploration | Inquiry threads, open loops, affect curiosity | Derived |
| 3 | Attention and Focus | RhythmTimeSteward peak hour and pacing | Derived |
| 4 | Memory and Retention | SM-2 cards plus episodic memory | Direct |
| 5 | Learning Velocity | New ZPD-normalized time-to-mastery state | Derived |
| 6 | Conceptual Understanding and Depth | MasteryTracker per-concept `p_mastery` | Direct |
| 7 | Problem Solving and Critical Thinking | Challenge state plus misconceptions | Proxy |
| 8 | Creativity and Imagination | Cross-domain pattern and awe/connection episodes | Proxy |
| 9 | Motivation and Drive | New voluntary return-after-difficulty state | Derived |
| 10 | Emotional Well Being and Family Environment | Affect vector plus consent-gated family context | Derived |
| 11 | Confidence and Self Efficacy | BeliefCoach and confidence calibration | Direct |
| 12 | Adaptability and Resilience | Productive-failure tolerance plus hard-turn returns | Proxy |
| 13 | Learning Preference | Register, language mix, analogy domains | Derived |
| 14 | Value and Purpose | Periodic reflection prompt and synthesis | Reflection |
| 15 | Social Learning and Collaboration | Revived social preference state | Direct |

Statuses are part of the API. A proxy dimension must not be displayed as a
clinical or high-stakes measurement.

## API Surface

- `GET /learner/{learner_id}/dimensions`
  - Builds and caches the current 15-dimension snapshot.
  - Each dimension includes `score`, `confidence`, `status`, `evidence`,
    `summary`, `next_action`, and owning agents.
- `GET /learner/{learner_id}/reflection-prompt`
  - Returns the next value/purpose prompt.
- `POST /learner/{learner_id}/reflection`
  - Stores one reflection and updates value/purpose state.

## Cold-Start Handoff

`/learner/register` now requires five persisted puzzle responses before it
auto-grants pilot consent. `/chat` can repair a failed handoff after five probes,
but it no longer bypasses cold start for a learner with no probe history.

The Flutter onboarding also handles the resume edge case where the fifth probe
was saved but registration did not finish. On the next launch, a normal puzzle
payload is treated as "cold start complete" and registration is retried.

## Onboarding Ideas

WhatsApp can reduce cold-start friction without replacing consent:

- Guardian pre-onboarding: parent shares child name, grade, preferred language,
  study time, and context through WhatsApp. This maps cleanly into the existing
  guardian onboarding questions and consent-gated family context.
- Teacher voice note: teacher sends a short WhatsApp voice note about the child.
  A future ingestion pass can produce a teacher portrait without exposing raw
  audio to chat.
- Mini cold-start before app install: WhatsApp sends two tap-choice curiosity
  probes and one voice/text reasoning prompt. The app still completes the full
  five-probe protocol before chat.
- Deep-link handoff: WhatsApp returns a signed setup link that opens Flutter with
  learner ID, grade, and consent state prefilled.
- Privacy guardrails: no sensitive family or wellbeing inference from WhatsApp
  without explicit guardian consent; raw WhatsApp content should be short-lived,
  with only typed, reviewable portrait fields persisted.

Next direct-measure upgrades:

- Add an explicit creativity prompt with rubric-scored novelty and usefulness.
- Add a direct critical-thinking rubric for claims, evidence, and counterexample
  handling.
- Add a resilience reflection after hard problems to distinguish healthy
  persistence from overexertion.
