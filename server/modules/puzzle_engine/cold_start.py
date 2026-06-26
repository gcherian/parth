"""
Cold Start Protocol — Portrait a Child in 5 Interactions
=========================================================

The fundamental problem: you cannot ask a child who they are.
At 8–13, children lack self-knowledge and answer with what they think
you want to hear. Every interaction must be a *behavioral probe*,
not a question.

The five probes are designed so that:
  - Each probe is maximally informative (reduces uncertainty the most)
  - Each probe is enjoyable regardless of outcome (no child should feel tested)
  - Together, they converge on the three things that matter most:
      1. What domain pulls this child? (sphere affinity)
      2. Where is the edge of their understanding? (ZPD)
      3. How do they respond when they can't immediately solve something? (error response)

After 5 probes Parth has enough to personalise substantially.
After 10 probes the portrait is reliable enough for parent communication.
After 20 probes the MBTI estimate is meaningful.

Information-theoretic framing
------------------------------
Each binary choice (probe 1 and 4) yields 1 bit of entropy reduction.
Probe 2 (ZPD performance) yields ~1.5 bits.
Probe 3 (error response) yields ~2 bits — the single richest signal.
Probe 5 (free expression) yields ~1 bit on depth/style.
Total: ~6.5 bits from 5 probes → distinguishes among ~90 profile types.

With grade-level priors this is sufficient for meaningful first personalisation.

Protocol API
------------
  GET /puzzle/cold-start/{learner_id}
      Returns the next cold-start probe as a structured choice or puzzle.

  POST /puzzle/cold-start/{learner_id}/respond
      Records the response; returns updated portrait fragment.

  GET /puzzle/portrait/{learner_id}
      Returns the synthesised child portrait.
"""
from __future__ import annotations

from modules.puzzle_engine.loader import (
    for_sphere, Puzzle, SPHERES, LEVEL_ORDER
)
import random

# ── Two maximally-different sphere pairs for the opening choice ──────────────
# Each pair is chosen so a child who picks one vs. the other reveals
# their primary pull (conceptual/symbolic vs. physical/embodied, etc.)
_PROBE_1_PAIRS = [
    ("philosophy_logic",     "biology_medicine"),
    ("mathematics",          "arts_interdisciplinary"),
    ("astronomy_cosmology",  "social_sciences"),
    ("physics",              "eastern_wisdom"),
    ("computer_science_ai",  "arts_interdisciplinary"),
]

# ── Sphere → canonical second-level pair for probe 2 ─────────────────────────
# After choosing a hemisphere, narrow to specific sphere
_PROBE_2_BRANCHES: dict[str, tuple[str, str]] = {
    "philosophy_logic":     ("mathematics",          "social_sciences"),
    "biology_medicine":     ("chemistry",            "astronomy_cosmology"),
    "mathematics":          ("physics",              "computer_science_ai"),
    "arts_interdisciplinary": ("eastern_wisdom",     "philosophy_logic"),
    "astronomy_cosmology":  ("physics",              "mathematics"),
    "social_sciences":      ("philosophy_logic",     "eastern_wisdom"),
    "physics":              ("mathematics",          "chemistry"),
    "eastern_wisdom":       ("philosophy_logic",     "astronomy_cosmology"),
    "computer_science_ai":  ("mathematics",          "physics"),
    "chemistry":            ("biology_medicine",     "physics"),
}

# ── Bridge pairs for probe 4 (cross-domain curiosity) ──────────────────────
# Maps primary sphere → maximally surprising but genuinely connected bridge sphere
_BRIDGES: dict[str, str] = {
    "mathematics":          "arts_interdisciplinary",   # Fibonacci in music; pi in poetry
    "arts_interdisciplinary": "mathematics",             # Golden ratio; harmonic series
    "physics":              "philosophy_logic",          # Mach vs Newton; Zeno paradoxes
    "philosophy_logic":     "mathematics",              # Gödel; Russell
    "biology_medicine":     "computer_science_ai",      # DNA as code; neural nets from neurons
    "computer_science_ai":  "biology_medicine",         # Genetic algorithms; neural nets
    "astronomy_cosmology":  "eastern_wisdom",           # Aryabhata predated Copernicus
    "eastern_wisdom":       "astronomy_cosmology",      # Varahamihira; Brahmagupta
    "chemistry":            "arts_interdisciplinary",   # Colour theory; material science in art
    "social_sciences":      "biology_medicine",         # Epidemiology; evolutionary psychology
}


def get_probe(
    probe_number: int,
    seen_ids: set[str],
    primary_sphere: str | None,
    grade: int = 6,
) -> dict:
    """
    Return the structured probe for step N of the cold start.

    Probe 1 — Binary sphere choice
        Returns two puzzle hooks from maximally different spheres.
        The child picks the hook that interests them more.
        No puzzle is served yet — only the hooks.

    Probe 2 — ZPD probe puzzle (serve intermediate level)
        In the chosen sphere: serve an intermediate puzzle.
        Even if Grade suggests beginner — we deliberately overshoot
        so we can observe how the child handles difficulty.

    Probe 3 — Error moment (built into evaluation, not a special puzzle)
        Serve a puzzle from chosen sphere at the same level.
        Parth's evaluator watches for the child's error response.

    Probe 4 — Bridge puzzle (cross-domain curiosity test)
        Serve a beginner puzzle from the BRIDGE sphere.
        Introduce it as: "Here's something surprising — can you see the connection?"

    Probe 5 — Free expression
        Serve any puzzle with go_deeper, then ask:
        "What was the most surprising thing you noticed? Tell me in your own words."
    """
    if probe_number in (0, 1):
        pair = random.choice(_PROBE_1_PAIRS)
        hook_a = _best_hook(pair[0], "beginner", seen_ids)
        hook_b = _best_hook(pair[1], "beginner", seen_ids)
        return {
            "probe": 1,
            "mode": "choice",
            "instruction": (
                "Which of these two questions makes you more curious? "
                "Pick the one you'd most like to explore."
            ),
            "option_a": hook_a,
            "option_b": hook_b,
        }

    if probe_number == 2:
        sphere = primary_sphere or "mathematics"
        # Deliberately serve intermediate to probe ZPD
        puzzle = _best_puzzle(sphere, "intermediate", seen_ids)
        if puzzle is None:
            puzzle = _best_puzzle(sphere, "beginner", seen_ids)
        return {
            "probe": 2,
            "mode": "puzzle",
            "note": "ZPD probe — one level above expected. Watch engagement vs. frustration.",
            "puzzle": puzzle,
        }

    if probe_number == 3:
        sphere = primary_sphere or "mathematics"
        puzzle = _best_puzzle(sphere, "beginner", seen_ids)
        return {
            "probe": 3,
            "mode": "puzzle",
            "note": "Error response probe — evaluator watches error reaction signals.",
            "puzzle": puzzle,
        }

    if probe_number == 4:
        bridge_sphere = _BRIDGES.get(primary_sphere or "mathematics", "philosophy_logic")
        puzzle = _best_puzzle(bridge_sphere, "beginner", seen_ids)
        return {
            "probe": 4,
            "mode": "puzzle",
            "instruction": (
                "Here's something surprising — a completely different subject "
                "that secretly connects to what you've been exploring. "
                "Can you see the connection after you try it?"
            ),
            "puzzle": puzzle,
        }

    if probe_number == 5:
        sphere = primary_sphere or "philosophy_logic"
        # Pick a puzzle that has a strong go_deeper
        puzzle = _best_puzzle_with_go_deeper(sphere, seen_ids)
        return {
            "probe": 5,
            "mode": "puzzle",
            "follow_up": (
                "After you finish: tell me one thing that surprised you, "
                "in your own words. There's no right answer."
            ),
            "puzzle": puzzle,
        }

    return {}


def _best_hook(sphere: str, level: str, seen_ids: set[str]) -> dict | None:
    puzzles = [p for p in for_sphere(sphere) if p["id"] not in seen_ids and p["level"] == level]
    if not puzzles:
        return None
    p = random.choice(puzzles[:5])
    return {"puzzle_id": p["id"], "sphere": sphere, "hook": p["hook"], "title": p["title"]}


def _best_puzzle(sphere: str, level: str, seen_ids: set[str]) -> Puzzle | None:
    puzzles = [p for p in for_sphere(sphere) if p["id"] not in seen_ids and p["level"] == level]
    return random.choice(puzzles[:5]) if puzzles else None


def _best_puzzle_with_go_deeper(sphere: str, seen_ids: set[str]) -> Puzzle | None:
    puzzles = [
        p for p in for_sphere(sphere)
        if p["id"] not in seen_ids and p.get("go_deeper", "").strip()
    ]
    return random.choice(puzzles[:5]) if puzzles else _best_puzzle(sphere, "beginner", seen_ids)
