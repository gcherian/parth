"""
Child Portrait — Synthesised from Behavioral Observations
=========================================================

The portrait is the primary instrument for personalisation.
It is NOT a questionnaire result — it is an inference from what the child
does, not what they say about themselves.

Five dimensions the portrait tracks (beyond the existing psyche model):

1. primary_sphere        — which domain pulls this child most?
2. zpd_level             — beginner | intermediate | advanced (per sphere)
3. error_response        — growth | fixed | avoidant | perfectionist
4. cross_domain_curiosity — does their interest transfer across domains?
5. provisional_telos     — explorer | builder | philosopher | artist | scientist

These are inferred from behavioral signals, not self-report.
Confidence starts at 0.0 and rises toward 1.0 with each interaction.

The portrait is injected into:
  - Puzzle selector (ZPD + sphere affinity)
  - Parth's system prompt (pedagogical calibration)
  - Krishna Oracle (strategic guidance)
  - Parent dashboard (readable summary via Krishna)
"""
from __future__ import annotations

import json
from typing import TypedDict


# ── Telos type definitions ─────────────────────────────────────────────────

TELOS_TYPES = {
    "explorer": {
        "description": "Drawn to discovery — asks WHY before HOW. Wants to understand "
                       "the deep reason something is true.",
        "best_hooks":  ["thought_experiment", "investigation", "observation"],
        "spheres":     ["astronomy_cosmology", "philosophy_logic", "eastern_wisdom"],
        "pi_bridge":   "orbital_mechanics",
        "parth_tone":  "Open with mystery: 'Here's something strange about the universe…' "
                       "Then let them discover the pattern.",
    },
    "builder": {
        "description": "Wants to make things work. Asks HOW before WHY. "
                       "Satisfaction comes from something functioning correctly.",
        "best_hooks":  ["experiment", "construction", "design"],
        "spheres":     ["mathematics", "computer_science_ai", "physics"],
        "pi_bridge":   "rolling_coin",
        "parth_tone":  "Lead with the doing: 'Let's build this.' Explain why afterward.",
    },
    "philosopher": {
        "description": "Questions assumptions. Asks WHETHER before HOW. "
                       "Interested in what should be, not just what is.",
        "best_hooks":  ["thought_experiment", "game", "proof"],
        "spheres":     ["philosophy_logic", "social_sciences", "eastern_wisdom"],
        "pi_bridge":   "leibniz_series",
        "parth_tone":  "Introduce the paradox first. What does this mean? Should it be true?",
    },
    "artist": {
        "description": "Seeks beauty and connection. Resonates with the aesthetic "
                       "dimension of ideas — elegance, pattern, surprise.",
        "best_hooks":  ["observation", "investigation", "pattern"],
        "spheres":     ["arts_interdisciplinary", "eastern_wisdom", "astronomy_cosmology"],
        "pi_bridge":   "nautilus_spiral",
        "parth_tone":  "Begin with the beautiful case. The mechanics follow naturally.",
    },
    "scientist": {
        "description": "Wants to verify. Asks IS IT ACTUALLY TRUE? Trusts evidence "
                       "over authority. Wants to measure before believing.",
        "best_hooks":  ["experiment", "investigation", "proof"],
        "spheres":     ["physics", "chemistry", "biology_medicine"],
        "pi_bridge":   "measure_and_verify",
        "parth_tone":  "Give them something to test. They trust what they measured themselves.",
    },
}

# ── Error response type definitions ──────────────────────────────────────────

ERROR_RESPONSES = {
    "growth": {
        "signal_patterns": ["tried again", "let me think", "oh i see", "so if i do",
                            "what if i", "maybe i should"],
        "parth_response": "Challenge slightly: 'Good — now here's the harder version.'",
        "avoid": "Never over-praise effort — they already know they can do better.",
    },
    "fixed": {
        "signal_patterns": ["i can't", "i'm bad at", "i'll never", "i'm just not",
                            "nahi kar sakta", "bahut mushkil"],
        "parth_response": (
            "Never use 'wrong' or 'incorrect'. Say 'not yet'. "
            "Ask what they DID understand — anchor to their competence first. "
            "Attribute outcome to strategy: 'That strategy didn't work — which one next?'"
        ),
        "avoid": "Do not praise intelligence ('you're so smart'). Praise process only.",
    },
    "avoidant": {
        "signal_patterns": ["can we do something else", "this is boring", "what about",
                            "never mind", "skip", "boring", "bakwas"],
        "parth_response": (
            "Follow them — pick up the concept in their new question. "
            "Indirection works: embed the stuck concept in something they chose."
        ),
        "avoid": "Do not insist. The moment of avoidance is a signal, not a failure.",
    },
    "perfectionist": {
        "signal_patterns": ["but i got part wrong", "that's not perfect", "i made a mistake",
                            "start over", "that's not exactly right"],
        "parth_response": (
            "Reframe: 'Getting one thing wrong means you understood nine things correctly. "
            "What were the nine?' Move forward — don't allow restart loops."
        ),
        "avoid": "Do not offer to start over. Do not validate the perfectionist framing.",
    },
}


class Portrait(TypedDict):
    learner_id: str
    primary_sphere: str
    secondary_sphere: str
    zpd_levels: dict          # sphere → level
    error_response: str       # growth | fixed | avoidant | perfectionist
    cross_domain_curiosity: float   # 0-1
    provisional_telos: str
    sphere_affinity: dict     # sphere → score 0-10
    confidence: float         # 0-1; grows with interactions
    interactions_used: int
    grade: int
    language_ratio: float     # 1.0=English, 0.0=Hindi


def default_portrait(learner_id: str, grade: int = 6) -> Portrait:
    return {
        "learner_id":             learner_id,
        "primary_sphere":         "",
        "secondary_sphere":       "",
        "zpd_levels":             {},
        "error_response":         "unknown",
        "cross_domain_curiosity": 0.5,
        "provisional_telos":      "explorer",
        "sphere_affinity":        {},
        "confidence":             0.0,
        "interactions_used":      0,
        "grade":                  grade,
        "language_ratio":         1.0,
    }


def confidence_level(n_interactions: int) -> float:
    """
    Confidence curve:
      1 interaction  → 0.12
      3 interactions → 0.32
      5 interactions → 0.50 (minimal useful personalisation)
      10 interactions → 0.72
      20 interactions → 0.88
    """
    return round(1.0 - 1.0 / (1.0 + 0.15 * n_interactions), 3)


def adaptive_alpha(n_interactions: int) -> float:
    """
    Adaptive EMA learning rate.
    Faster in the cold start (high uncertainty), slower once portrait is stable.
    """
    if n_interactions < 5:   return 0.45
    if n_interactions < 15:  return 0.25
    if n_interactions < 40:  return 0.15
    return 0.10


def update_sphere_affinity(
    affinity: dict[str, float],
    sphere: str,
    quality: int,         # 0-3 from puzzle response
    n: int,               # total interactions so far
) -> dict[str, float]:
    """Update sphere affinity EMA from a puzzle response quality score (0-3)."""
    alpha = adaptive_alpha(n)
    # Convert quality 0-3 to engagement 1-10
    engagement = {0: 2.0, 1: 5.0, 2: 7.5, 3: 10.0}.get(quality, 5.0)
    old = affinity.get(sphere, 5.0)
    affinity[sphere] = round((1 - alpha) * old + alpha * engagement, 3)
    return affinity


def infer_telos(
    sphere_affinity: dict[str, float],
    psyche: dict,
    probe_4_engaged: bool,   # did child follow the cross-domain bridge?
    go_deeper_rate: float,   # fraction of puzzles where child attempted go_deeper
) -> str:
    """
    Infer provisional telos from behavioral signals.

    This is a heuristic classifier, not a ground truth.
    It is labelled 'provisional' and updated every 10 interactions.
    """
    depth   = psyche.get("depth_preference", 0.5)
    logic   = psyche.get("thinking_feeling", 0.5)
    social  = psyche.get("extroversion", 0.5)

    top_sphere = max(sphere_affinity, key=sphere_affinity.get) if sphere_affinity else ""

    if top_sphere in ("philosophy_logic", "eastern_wisdom") and depth > 0.60:
        return "philosopher"

    if top_sphere in ("arts_interdisciplinary",) and depth < 0.55:
        return "artist"

    if top_sphere in ("arts_interdisciplinary",) and probe_4_engaged:
        return "artist"

    if top_sphere in ("computer_science_ai", "mathematics") and logic > 0.65:
        return "builder"

    if top_sphere in ("physics", "chemistry", "biology_medicine") and go_deeper_rate < 0.4:
        return "scientist"

    if probe_4_engaged and depth > 0.55 and go_deeper_rate > 0.5:
        return "explorer"

    # Default
    if depth > 0.60:
        return "explorer"
    if logic > 0.65:
        return "builder"
    return "explorer"


def infer_error_response(
    anxiety: float,
    growth_mindset: float,
    abandonment_rate: float,   # fraction of puzzles where child stopped at challenge
    completion_rate: float,    # fraction of puzzles where child reached discover
) -> str:
    """
    Classify primary error response pattern from behavioral signals.
    """
    if growth_mindset > 0.65 and abandonment_rate < 0.2:
        return "growth"
    if anxiety > 0.65 or (abandonment_rate > 0.5 and growth_mindset < 0.45):
        return "fixed"
    if abandonment_rate > 0.4 and anxiety < 0.5:
        return "avoidant"
    if completion_rate > 0.8 and anxiety > 0.45:
        return "perfectionist"
    return "growth"


def build_portrait_context(portrait: Portrait, psyche: dict) -> str:
    """
    Produces the portrait block injected into Parth's system prompt.
    Concise — 6-10 lines maximum.
    """
    if portrait["confidence"] < 0.20:
        return ""   # not enough data yet

    telos_info = TELOS_TYPES.get(portrait["provisional_telos"], {})
    error_info = ERROR_RESPONSES.get(portrait["error_response"], {})

    sphere = portrait["primary_sphere"].replace("_", " ")
    level  = portrait["zpd_levels"].get(portrait["primary_sphere"], "beginner")
    telos  = portrait["provisional_telos"]

    lines = [
        f"Child portrait (confidence: {portrait['confidence']:.0%}):",
        f"Primary interest: {sphere} at {level} level",
        f"Learning type: {telos} — {telos_info.get('description', '')}",
    ]

    if portrait["error_response"] != "unknown":
        lines.append(f"Error response: {portrait['error_response']} — {error_info.get('parth_response', '')}")

    if portrait["cross_domain_curiosity"] > 0.60:
        lines.append("Responds well to cross-domain bridges — use subject fusion.")
    elif portrait["cross_domain_curiosity"] < 0.35:
        lines.append("Prefers to stay within one domain — avoid rapid subject-switching.")

    if telos_info.get("parth_tone"):
        lines.append(f"Teaching tone: {telos_info['parth_tone']}")

    avoid = error_info.get("avoid", "")
    if avoid:
        lines.append(f"AVOID: {avoid}")

    return "\n".join(lines)
