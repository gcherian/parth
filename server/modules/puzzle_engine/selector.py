"""
Puzzle Selector — ZPD-aware, sphere-affinity-weighted next puzzle chooser.

Selection priority (highest to lowest):
  1. Onboarding protocol (first 5 puzzles) — cold-start sphere sweep
  2. ZPD match: target level = current mastery level + 0 or +1
  3. Sphere affinity: prefer spheres the child gravitates toward
  4. Anti-monotony: avoid ≥ 3 consecutive puzzles from the same sphere
  5. No repeats: never serve a puzzle the child has already seen
  6. Telos alignment: if telos is set, weight telos-aligned spheres ×1.5

Vygotsky ZPD:
  - mastery < 0.4 in sphere  → beginner puzzles
  - mastery 0.4–0.7           → intermediate
  - mastery > 0.7             → advanced
"""
from __future__ import annotations

import random
from typing import Any

from modules.puzzle_engine.loader import (
    Puzzle, SPHERES, LEVEL_ORDER, for_sphere, spheres_available
)

# Telos → sphere affinity boosters
_TELOS_SPHERES: dict[str, list[str]] = {
    "explorer":    ["astronomy_cosmology", "biology_medicine", "eastern_wisdom"],
    "builder":     ["mathematics", "computer_science_ai", "physics"],
    "philosopher": ["philosophy_logic", "social_sciences", "eastern_wisdom"],
    "artist":      ["arts_interdisciplinary", "philosophy_logic", "eastern_wisdom"],
    "scientist":   ["physics", "chemistry", "biology_medicine"],
}

_ONBOARDING_SPHERES = [
    "mathematics",
    "arts_interdisciplinary",
    "philosophy_logic",
    "astronomy_cosmology",
    "biology_medicine",
]


def _sphere_level(sphere_mastery: float) -> str:
    if sphere_mastery < 0.4:
        return "beginner"
    if sphere_mastery < 0.72:
        return "intermediate"
    return "advanced"


def _score_sphere(
    sphere: str,
    affinity: dict[str, float],
    telos: str,
    last_sphere: str,
    consecutive: int,
) -> float:
    base = affinity.get(sphere, 5.0)
    if telos and sphere in _TELOS_SPHERES.get(telos, []):
        base *= 1.5
    if sphere == last_sphere and consecutive >= 2:
        base *= 0.3   # strong anti-monotony penalty
    elif sphere == last_sphere:
        base *= 0.7
    return base


def next_puzzle(
    seen_ids: set[str],
    sphere_affinity: dict[str, float],
    sphere_mastery: dict[str, float],
    total_puzzles: int,
    last_sphere: str,
    consecutive_sphere: int,
    telos: str = "",
    grade: int = 6,
) -> Puzzle | None:
    available = spheres_available()

    # ── Onboarding: first 5 puzzles sweep across spheres ─────────────────
    if total_puzzles < 5:
        idx = total_puzzles % len(_ONBOARDING_SPHERES)
        sphere = _ONBOARDING_SPHERES[idx]
        candidates = [p for p in for_sphere(sphere)
                      if p["id"] not in seen_ids and p["level"] == "beginner"]
        if candidates:
            return random.choice(candidates)

    # ── Normal selection ──────────────────────────────────────────────────
    # Score and rank spheres
    scored = sorted(
        available,
        key=lambda s: _score_sphere(s, sphere_affinity, telos, last_sphere, consecutive_sphere),
        reverse=True,
    )

    for sphere in scored:
        mastery = sphere_mastery.get(sphere, 0.0)
        target_level = _sphere_level(mastery)

        candidates = [
            p for p in for_sphere(sphere)
            if p["id"] not in seen_ids and p["level"] == target_level
        ]

        # If no puzzles at target level, try one level easier (graceful degradation)
        if not candidates:
            easier = "beginner" if target_level == "intermediate" else "intermediate"
            candidates = [
                p for p in for_sphere(sphere)
                if p["id"] not in seen_ids and p["level"] == easier
            ]

        if candidates:
            # Weighted random — slight randomness keeps it from being mechanical
            return random.choice(candidates[:5])   # top 5 candidates

    return None   # all puzzles seen (shouldn't happen with 300 puzzles)
