"""
Bayesian Knowledge Tracing — the standard 4-parameter per-skill HMM.

Replaces the ratio heuristic that used to live in knowledge.py's `_mastery()`
(see docs/model_of_the_child_2026_09_18.md §3.3 for why that was never
actually BKT despite the docstring). This module is the literal math; the
per-concept/global parameter lookup and the DB read/write glue stay in
knowledge.py, same as before.

    p_init     — P(the child already knows this skill, before any evidence)
    p_transit  — P(learns the skill on one opportunity to practice it)
    p_slip     — P(answers wrong despite actually knowing the skill)
    p_guess    — P(answers right despite not knowing the skill)

One `update()` call does the textbook two-step BKT recurrence:
  1. Bayes' rule: fold the observed correct/incorrect into the current
     P(mastery) using p_slip/p_guess to get P(mastery | this observation).
  2. Learning transition: some non-zero chance the child learned the skill
     during this attempt regardless of the observation, so nudge the
     posterior toward 1.0 by p_transit.

Fit via server/fit_bkt_params.py (grid search maximizing log-likelihood
against learner_state.kt_events) — see that script for methodology and how
to refit as data grows.
"""
from __future__ import annotations

from dataclasses import dataclass

# Floor/ceiling match the old heuristic's clamp range, so downstream readers
# (weak_concepts/strong_concepts thresholds, dimensions.py) keep working on
# the same [0.05, 0.98]-ish scale without needing their own thresholds retuned.
_FLOOR = 0.05
_CEILING = 0.98


@dataclass(frozen=True)
class BKTParams:
    p_init: float
    p_transit: float
    p_slip: float
    p_guess: float

    def __post_init__(self):
        for name in ("p_init", "p_transit", "p_slip", "p_guess"):
            v = getattr(self, name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"BKTParams.{name}={v!r} must be in [0, 1]")


# Used only if learner_state.bkt_params has no rows at all yet (a brand-new
# deployment before fit_bkt_params.py has ever run). Once that script runs
# once, its fitted "_global_" row takes over — see knowledge.get_params().
LITERATURE_DEFAULTS = BKTParams(p_init=0.30, p_transit=0.15, p_slip=0.10, p_guess=0.20)


def initial(params: BKTParams) -> float:
    """P(mastery) before the child has attempted this concept at all."""
    return params.p_init


def update(prior: float, correct: bool, params: BKTParams) -> float:
    """One Bayes update + learning transition. Returns the new P(mastery)."""
    prior = min(max(prior, 0.0), 1.0)
    if correct:
        numerator = prior * (1.0 - params.p_slip)
        denominator = numerator + (1.0 - prior) * params.p_guess
    else:
        numerator = prior * params.p_slip
        denominator = numerator + (1.0 - prior) * (1.0 - params.p_guess)

    posterior_given_evidence = numerator / denominator if denominator > 0 else prior
    posterior = posterior_given_evidence + (1.0 - posterior_given_evidence) * params.p_transit
    return round(min(_CEILING, max(_FLOOR, posterior)), 4)


def predict_correct(prior: float, params: BKTParams) -> float:
    """P(correct on the next attempt), given current P(mastery). Used by
    eval_knowledge_model.py to score next-step predictions — not called by
    the live update path, which only needs `update()`."""
    prior = min(max(prior, 0.0), 1.0)
    return prior * (1.0 - params.p_slip) + (1.0 - prior) * params.p_guess
