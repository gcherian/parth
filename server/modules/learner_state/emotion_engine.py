"""
Emotion Model v2 — continuous (valence, intensity) affect engine.

Replaces "pick one discrete label every turn" with a state that is integrated
turn-over-turn, biased by which affect transitions are actually common during
learning (D'Mello & Graesser 2012) rather than treating every transition as
equally likely. See EMOTION_MODEL_V2_DESIGN.md for the research this is built
on and the production integration plan.

This module is intentionally dependency-free (no DB, no LLM client) so it can
be unit-tested and driven by tests/simulate_peer_emotion.py in isolation.
Discrete labels are a *projection* of the continuous state, using the exact
vocabulary already in evaluator.py / learner_state/signals.py, so existing
prompts and DB columns keep working unchanged if this is wired in later.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# ── Continuous state ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EmotionState:
    valence: float = 0.0     # -1.0 (very unpleasant) .. +1.0 (very pleasant)
    intensity: float = 0.2   #  0.0 (deactivated/flat) ..  1.0 (highly activated)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ── Discrete label vocabulary (matches evaluator.py / learner_state/signals.py) ─
# Kept identical to the existing system's label set so this is a drop-in
# projection, not a new taxonomy to migrate consumers onto.

REGIONS = (
    "distressed", "frustrated", "anxious", "confused",
    "curious", "excited", "disengaged", "neutral",
)


def project(state: EmotionState) -> str:
    """Map a continuous (valence, intensity) point onto the existing discrete
    label vocabulary. This is a read-out for humans/prompts — the state itself
    is the source of truth."""
    v, a = state.valence, state.intensity
    if v <= -0.6 and a >= 0.6:
        return "distressed"
    if v <= -0.3 and a >= 0.45:
        return "frustrated"
    if v <= -0.15 and a >= 0.3:
        return "anxious"
    if abs(v) < 0.2 and 0.25 <= a < 0.6:
        return "confused"
    if v >= 0.55 and a >= 0.55:
        return "excited"
    if v >= 0.25 and a >= 0.3:
        return "curious"
    if v <= -0.15 and a < 0.3:
        return "disengaged"
    return "neutral"


# ── Appraisal: turn content -> (delta_valence, delta_intensity) impulse ────────
# Continuous version of learner_state/signals.py's _EMOTION_PATTERNS: instead
# of picking one label, every matching family contributes a weighted pull
# toward its (valence, intensity) target, so mixed-signal messages ("that's so
# hard but wait— OHHH") land somewhere between confused and excited rather
# than forcing one label.

_APPRAISAL_LEXICON: dict[str, tuple[float, float, re.Pattern]] = {
    "distressed": (-0.85, 0.85, re.compile(
        r"\b(distressed|panicking|scared|failing|going to fail|will fail|"
        r"dar lag raha|stress|stressed out|crying|want to cry)\b", re.I)),
    "frustrated": (-0.70, 0.70, re.compile(
        r"\b(frustrated|i give up|give up|too hard|can't do|cant do|impossible|"
        r"nahi kar sakta|nahi samajh|bahut mushkil|this is hard|so hard|fed up|ugh)\b", re.I)),
    "anxious": (-0.50, 0.55, re.compile(
        r"\b(anxious|worried|nervous|what if i fail|exam kal hai|kal exam|tension)\b", re.I)),
    "confused": (-0.15, 0.40, re.compile(
        r"\b(confused|don't understand|don't get|kya matlab|samjha nahi|what is|why is|how does)\b", re.I)),
    "curious": (0.45, 0.50, re.compile(
        r"\b(what if|can we|tell me more|why does|how come|and then|next|more)\b", re.I)),
    "excited": (0.80, 0.75, re.compile(
        r"\b(wow|amazing|awesome|great|maza|cool!|love this|so interesting|incredible|no way)\b", re.I)),
    "disengaged": (-0.35, 0.15, re.compile(
        r"\b(boring|don't care|whatever|bakwas|don't want|hate (this|math|science))\b", re.I)),
    # Breakthrough/insight phrasing — not in the original single-label regex
    # vocabulary (learner_state/signals.py) but a common enough turn shape
    # that leaving it unrecognized was masking exactly the resolved-confusion
    # moment the transition graph cares about most.
    "insight": (0.65, 0.55, re.compile(
        r"\b(i get it|i got it|oh my god i|got it!|that makes sense|makes sense now|"
        r"oh i see|i see now|now i understand|i understand now|acha samjha|samajh gaya|samajh gayi)\b", re.I)),
}

_CAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")


def appraise_text(text: str) -> tuple[float, float, list[str]]:
    """Turn message text into an appraisal impulse (dv, di) plus which lexicon
    families matched. Multiple matches are averaged (weighted by hit count),
    not first-match-wins — a message can be simultaneously a bit confused and
    a bit curious."""
    hits: list[tuple[float, float]] = []
    matched: list[str] = []
    for label, (v, a, pattern) in _APPRAISAL_LEXICON.items():
        n = len(pattern.findall(text))
        if n:
            hits.append((v, a, n))
            matched.append(label)

    if not hits:
        dv, di = 0.05, 0.15  # mild, low-intensity default: unremarkable turn
    else:
        total = sum(n for _, _, n in hits)
        dv = sum(v * n for v, _, n in hits) / total
        di = sum(a * n for _, a, n in hits) / total

    # Punctuation/caps push intensity up without changing valence sign —
    # "!!!" or shouting reads as *more* of whatever is already being expressed.
    excitement_markers = text.count("!") + len(_CAPS_WORD_RE.findall(text))
    di = _clip(di + 0.05 * min(excitement_markers, 3), 0.0, 1.0)

    return _clip(dv, -1.0, 1.0), di, matched


# ── Transition graph — D'Mello & Graesser (2012) oscillation structure ────────
# Symmetric edge weights between discrete regions: how readily the state
# integrates toward an appraisal landing in a *different* region than the one
# it's currently in. High weight = documented, common oscillation (confusion
# resolving into flow, or into frustration; boredom and frustration feeding
# each other). Low weight = a jarring jump the model damps down rather than
# taking at face value (bored -> excited in one turn is rare in practice).

_STRONG_EDGES = {
    frozenset({"confused", "curious"}),
    frozenset({"confused", "excited"}),
    frozenset({"confused", "frustrated"}),
    frozenset({"confused", "anxious"}),
    frozenset({"disengaged", "frustrated"}),
    frozenset({"disengaged", "anxious"}),
}
_DAMPED_EDGES = {
    frozenset({"disengaged", "excited"}),
    frozenset({"disengaged", "curious"}),
    frozenset({"frustrated", "excited"}),
    frozenset({"frustrated", "curious"}),
    frozenset({"distressed", "excited"}),
    frozenset({"distressed", "curious"}),
}

_EDGE_STRONG = 0.90
_EDGE_DAMPED = 0.25
_EDGE_DEFAULT = 0.55


def edge_weight(region_now: str, region_target: str) -> float:
    if region_now == region_target:
        return _EDGE_STRONG
    pair = frozenset({region_now, region_target})
    if pair in _STRONG_EDGES:
        return _EDGE_STRONG
    if pair in _DAMPED_EDGES:
        return _EDGE_DAMPED
    return _EDGE_DEFAULT


# ── Integration ("one thought leads to another", not a jump) ─────────────────

K_V = 0.55          # base integration gain, valence
K_A = 0.55          # base integration gain, intensity
NOISE_STD = 0.03     # small stochastic drift so identical inputs don't produce
                     # a perfectly deterministic trajectory


def step(state: EmotionState, dv: float, di: float, rng: random.Random) -> EmotionState:
    """Integrate one appraisal impulse into the current state. The new state
    is a damped pull toward (dv, di), not a replacement — the previous state
    is always part of the computation, which is the core fix over the current
    system's `last_emotion = new_label` overwrite."""
    region_now = project(state)
    region_target = project(EmotionState(valence=dv, intensity=di))
    w = edge_weight(region_now, region_target)

    new_v = state.valence + K_V * w * (dv - state.valence) + rng.gauss(0, NOISE_STD)
    new_a = state.intensity + K_A * w * (di - state.intensity) + rng.gauss(0, NOISE_STD)
    return EmotionState(valence=_clip(new_v, -1.0, 1.0), intensity=_clip(new_a, 0.0, 1.0))


CONTAGION_WEIGHT_CAP = 0.30  # peer pull is always weaker than self-appraisal


def contagion_step(state: EmotionState, other: EmotionState, trust: float,
                    rng: random.Random) -> EmotionState:
    """Hatfield-style convergence: pull toward a trusted peer's state, scaled
    by trust (0 = stranger, unaffected; 1 = close friend, full contagion
    weight). This is applied *in addition to* a student's own appraisal of the
    conversation content, never in place of it. trust=0 is an exact no-op —
    a stranger's state must not leak in even as noise."""
    w = CONTAGION_WEIGHT_CAP * _clip(trust, 0.0, 1.0)
    if w <= 0.0:
        return state
    new_v = state.valence + w * (other.valence - state.valence) + rng.gauss(0, NOISE_STD / 2 * w)
    new_a = state.intensity + w * (other.intensity - state.intensity) + rng.gauss(0, NOISE_STD / 2 * w)
    return EmotionState(valence=_clip(new_v, -1.0, 1.0), intensity=_clip(new_a, 0.0, 1.0))


# ── Gear-shift intervention policy ─────────────────────────────────────────────

def gear_shift(history: list[EmotionState], window: int = 3) -> str:
    """Read the *trajectory* (recent slope), not just the current point, so an
    intervention can fire while a shift is still in motion rather than after a
    negative state has already consolidated."""
    if len(history) < 2:
        return "hold_steady"

    recent = history[-window:]
    dv = recent[-1].valence - recent[0].valence
    di = recent[-1].intensity - recent[0].intensity

    if dv < -0.15 and di > 0.05:
        return "frustration_ramp -> simplify_or_hint_now"
    if -0.10 <= dv <= 0.05 and recent[-1].valence < 0.1 and di < -0.05:
        return "boredom_drift -> inject_novelty"
    if dv > 0.10 and di > 0.05:
        return "curiosity_building -> lean_in_deepen"
    if recent[-1].valence > 0.30 and di < -0.05:
        return "satisfied_winddown -> consolidate_praise"
    if recent[0].valence < -0.15 and recent[-1].valence > -0.05:
        return "resolved_from_negative -> reinforce_and_cement"
    return "hold_steady"


# ── Per-student engine ─────────────────────────────────────────────────────────

@dataclass
class StudentEmotionEngine:
    """Owns one student's continuous emotion trajectory across a conversation
    (with the tutor, or with a peer)."""
    student_id: str
    state: EmotionState = field(default_factory=EmotionState)
    history: list[EmotionState] = field(default_factory=list)
    seed: int | None = None
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        if not self.history:
            self.history = [self.state]

    def absorb_text(self, text: str) -> EmotionState:
        """Self-appraisal step: fold this message's content into the trajectory."""
        dv, di, _matched = appraise_text(text)
        self.state = step(self.state, dv, di, self._rng)
        self.history.append(self.state)
        return self.state

    def absorb_contagion(self, other: EmotionState, trust: float) -> EmotionState:
        """Peer-influence step: pull toward a trusted interlocutor's state."""
        self.state = contagion_step(self.state, other, trust, self._rng)
        self.history.append(self.state)
        return self.state

    @property
    def label(self) -> str:
        return project(self.state)

    def gear_shift(self, window: int = 3) -> str:
        return gear_shift(self.history, window=window)
