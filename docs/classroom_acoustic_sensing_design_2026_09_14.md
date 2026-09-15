# Classroom acoustic sensing — design exploration, not a build plan

Status: **design only, no code**. Written at the user's request while they
review the 8-gap PR batch with their cofounder. This is deliberately
structured like the business plan's own `DECISION REQUIRED` / `VERIFY`
convention — the open questions are the point, not a gap to paper over.

## 0. Why this gets its own framing before anything else

Invariant 03 (business plan §9) exists for a specific, named reason: *"Never
use the camera for monitoring... raw signals never leave the phone; only
coarse state is transmitted."* The reason it's a hard invariant, not a
feature flag, is trust — a parent's fear (Table 2, §2) is "that she is being
sold to again," and a teacher's fear is "that technology is coming for his
livelihood... that a parent will ask about a child he cannot answer."

Whole-classroom audio sensing is not a small extension of that invariant —
it's a materially bigger version of the exact thing the invariant was
written to rule out, for a reason worth stating plainly: **a camera pointed
at one consented child is a privacy problem with one data subject; a
microphone (or array of them) picking up an entire room is a privacy
problem with twenty-plus data subjects, most of whom never consented to
anything, including the teacher.**

So before signal design, the one framing decision that actually matters:

| Scope | What it captures | Who's a data subject | Legal/trust category |
|---|---|---|---|
| **A — own-device, own-session** | The enrolled child's own voice, during their own Parth session, on their own consented device | The one already-consented child | A natural extension of what's already built — same standing as the text chat Parth already processes |
| **B — room-scale, multi-device** | Every voice in mic range — other children, the teacher, whoever else is in the room — for direction, localization, or room-activity sensing | Every person in the room, none of whom (except the enrolled child) has any relationship with Parth at all | A different category of problem: surreptitious recording of non-users, not just a data-protection question |

Everything below is organized around that split, because the honest answer
to "design it" is that scope A and scope B don't belong in the same
build decision at all.

## 1. Signal categories ("everything you can imagine")

### I. Scope A — per-child vocal affect (low new risk, high value)
Derived only from the consented child's own voice during their own turn in
the existing tutor session:
- Speech rate, pause length, disfluency rate, pitch variance — feeds
  directly into the already-modeled persona dimensions 07–09 (Sessional
  emotion, Stress signature, Effort-vs-ability attribution) as a richer
  signal than text alone.
- Turn-taking ratio (how much the child talks vs. is talked to) within
  their own session.
- Ambient noise floor *around the child specifically*, as a coarse proxy
  for whether their immediate environment is chaotic — useful context for
  interpreting a struggling session, not a room-sensing feature.

This is the one category I'd actually recommend pursuing near-term. It's
architecturally identical to what Invariant 03 already permits (on-device
extraction, coarse state only, one consented stakeholder) — see §3 for the
concrete reuse path.

### II. Scope B — multi-device direction / localization
This is the "two/many speakers... interaural time differences" idea,
translated into the actual technique it maps to:

- **Correct framing**: not ITD (that's specifically the ~cm-scale ear-to-ear
  case), but **TDOA (time-difference-of-arrival) multilateration** across
  spatially separated microphones — phones or tablets placed around the
  room. The standard algorithm is **GCC-PHAT** (generalized cross-correlation
  with phase transform) run pairwise across devices, which is robust to
  reverberant, noisy real rooms in a way raw cross-correlation isn't —
  relevant here because a real tuition room (concrete walls, tin roof,
  30 children) is a much harder acoustic environment than a lab.
- **What it would need**: known/measured mic positions, clock
  synchronization across devices (acoustic chirp-based sync is the usual
  trick when you can't rely on network time), and a reference geometry that
  has to be re-established every time devices move — which, in a tuition
  room with phones on a shared table or in pockets, is often.
- **What it would buy, pedagogically, if it worked**: which part of the
  room is loudest/most chaotic; a crude "is the teacher spending physical
  proximity time near the back row" equity signal; where a specific child
  sits relative to the teacher, as weak context for engagement.
- **What it costs**: every additional device in the array is sensing every
  child and the teacher within its mic range, not just its owner. That
  makes each device a new consent problem, not just a new sensor.

### III. Scope B (active) — Doppler / near-ultrasonic sensing for "expansion"
The idea, made concrete: emit a fixed near-ultrasonic tone (~18–20kHz) from
a classroom-present speaker, listen for Doppler-shifted reflections off
moving bodies, and use aggregate positive-vs-negative shift energy across a
time window as a coarse "room activity/dispersal index" — kids standing up
and moving apart reads as one direction of shift, settling back into seats
the other. This is real, precedented HCI technique (acoustic-Doppler
gesture/presence sensing — the same family as MSR's *SoundWave* and
similar "speaker-as-radar" systems), not speculative.

Real caveats worth stating rather than discovering later:
- **"Inaudible" is not a safe assumption for this age group.** Adult
  high-frequency hearing rolls off well before 20kHz; an 11–14-year-old's
  does not. A tone designed to be inaudible to the adults who approved the
  pilot could be audible — and irritating — to exactly the children in the
  room. This needs real audiological verification, not an assumption.
- Multipath in a real room with 20–30 moving bodies is signal soup, not a
  single clean Doppler target — this degrades from "one gesture, one
  reflector" (the lab case it's proven in) to "many overlapping reflectors,"
  which is a much harder estimation problem than the technique was
  validated for.
- Continuous active emission has real battery/thermal cost on a phone
  speaker not designed for sustained ultrasonic output.

### IV. The hard boundary, regardless of category
None of the above should extend to actually transcribing or understanding
the *content* of anyone's speech other than the enrolled child's, during
their own session. This is a recommendation, not a technical limitation —
even a perfectly on-device, coarse-output architecture (the pattern that
makes Invariant 03's camera case defensible) doesn't neutralize this,
because for classroom speech content, the sensitive artifact is the words
themselves, spoken by people who aren't Parth users at all. "On-device
processing, coarse state transmitted" is a good answer to "don't leak a
video frame." It is not a good answer to "don't listen to what the
teacher's other twenty-nine students and the teacher himself are saying."

## 2. Architecture pattern, if scope A is pursued

Reuse the shape that already exists and was just built in PR #12
(`server/modules/attention_coarse` — `POST /attention/coarse-state`,
hard-rejects anything raw-signal-shaped, stores only an enum). The same
receiving contract extends naturally:

```
mic capture (own device, own session)
  → on-device feature extraction (pitch/rate/pause/disfluency)
  → discretize into a small fixed vocabulary of buckets
  → POST /attention/coarse-state  {child_id, session_id, state, ts}
      (extend the existing enum, or add a parallel `vocal_affect` field —
       same rejection rule: no raw waveform, no spectrogram, ever)
```

No new server-side module needed for scope A — it's an on-device feature
extractor feeding an endpoint that already exists and already enforces
"coarse only" as a hard server-side rule, not a client promise.

Scope B, if it were ever pursued, is a different architecture entirely —
each device in the array becomes its own trust surface, and the "coarse
state only" pattern doesn't resolve the underlying issue (see §1.IV), so
I haven't designed a wire format for it here. That's deliberate, not an
omission — the open question is whether to build it at all, not how.

## 3. `DECISION REQUIRED` — before any of scope B is built

1. **Does a classroom-audio feature undermine the teacher-channel
   thesis itself?** The plan's entire go-to-market (§3.5, §13) rests on the
   teacher trusting Parth enough to hand it his students. "Parth listens to
   the room" is a one-sentence pitch a competitor, a journalist, or an
   anxious parent could use to destroy that trust overnight, regardless of
   how careful the actual architecture is — perception risk, not just
   technical risk.
2. **DPDP doesn't cover this.** The existing consent architecture (§9.1)
   is per-(child, parent). Room audio unavoidably captures children whose
   parents never consented, and the teacher, who isn't a "user" in the
   consent model at all. This needs its own legal opinion — likely the same
   counsel the plan already earmarks for the DigiLocker question
   (Appendix F.2) — before scope B is anything but a design doc.
3. **Recording-of-third-parties law is a separate legal category from
   data protection**, and I haven't researched India's specific position
   here — flagging that this needs dedicated legal research, not treating
   DPDP compliance as sufficient.
4. **Audiological verification** of any "inaudible" tone against the actual
   target age band, not an assumption carried over from adult-hearing norms.

## 4. Recommendation

Build scope A (per-child vocal affect, own device, own session) if/when the
persona-model roadmap wants richer affect signal than text alone gives —
it's a small, well-bounded extension of an architecture pattern that
already exists and already shipped (PR #12). Treat scope B (multi-device
localization, active Doppler room sensing) as explicitly gated behind a
legal/trust review this document doesn't attempt to resolve — not as a
natural v2 of scope A, and possibly not as something to build at all, given
how directly it cuts against the plan's own central bet.
