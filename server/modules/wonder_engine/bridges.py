"""
wonder.engine — cross-domain discovery detours, offered during ordinary
chat rather than only during puzzle_engine's 5-turn cold-start window.

Reuses, rather than reinvents: the 300-puzzle library (puzzle_engine's
loader.py, "discovered, not delivered"), the cross-domain bridge map
(puzzle_engine/cold_start.py's bridge_for()), and curiosity signal
tracking (learner_state/curiosity.py). This file adds only what's new:
subject→sphere/level mapping, cadence gating, and prompt formatting.
"""
from __future__ import annotations

from foundation.observability import get_logger
from modules.puzzle_engine import loader
from modules.puzzle_engine.cold_start import bridge_for

log = get_logger("wonder.engine")

_SUBJECT_TO_SPHERE = {
    "science": "physics",
    "maths": "mathematics",
    "math": "mathematics",
    "mathematics": "mathematics",
    "history": "social_sciences",
    "social science": "social_sciences",
    "geography": "social_sciences",
    "hindi": "arts_interdisciplinary",
    "english": "arts_interdisciplinary",
}
_DEFAULT_SPHERE = "philosophy_logic"


def home_sphere(subject: str) -> str:
    return _SUBJECT_TO_SPHERE.get((subject or "").strip().lower(), _DEFAULT_SPHERE)


def level_for_grade(grade: int) -> str:
    if grade <= 6:
        return "beginner"
    if grade <= 10:
        return "intermediate"
    return "advanced"


def select_bridge_puzzle(subject: str, grade: int, exclude_ids: set[str]) -> dict | None:
    """Pick one puzzle from the sphere that bridges *away* from the
    learner's current subject (physics -> philosophy_logic, mathematics ->
    arts_interdisciplinary, ...) — the same cross-domain design as
    cold_start.py's Bridge puzzle, just usable every session instead of
    once. Falls back to an adjacent level if the exact level is exhausted
    (recently offered), matching selector.py's own fallback convention."""
    sphere = bridge_for(home_sphere(subject))
    level = level_for_grade(grade)

    for lvl in [level, "intermediate", "beginner", "advanced"]:
        candidates = [p for p in loader.for_sphere_level(sphere, lvl) if p["id"] not in exclude_ids]
        if candidates:
            return candidates[0]
    return None


def format_wonder_offer(puzzle: dict) -> str:
    return (
        f"Optional discovery detour (only offer this if it fits naturally in the "
        f"conversation — never force it, never let it replace answering what the "
        f"child actually asked): \"{puzzle['hook']}\" "
        f"If they're curious, guide them toward it themselves rather than "
        f"explaining the answer — the insight worth reaching is: {puzzle['discover']} "
        f"Let them discover that; don't just state it."
    )


def format_belief_exploration(misconception_hint: str) -> str:
    return (
        f"This child has previously reasoned their way to a belief that isn't quite "
        f"right: \"{misconception_hint}\". Before correcting it, if the moment is "
        f"right, acknowledge *why* that's a reasonable conclusion from what they've "
        f"observed, and propose something they could test or think through — rather "
        f"than opening with a correction. A wrong belief reached through real "
        f"reasoning is a hypothesis worth investigating, not just an error to fix."
    )
