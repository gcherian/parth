"""
Puzzle Loader — indexes the V2 puzzle library at startup.

The V2 library (data/puzzles/v2/) contains 10 sphere JSON files,
100 thinkers, 300 puzzles (3 per thinker × 3 levels).

All data is loaded once into memory at import time.
The library is ~200 KB — negligible RAM footprint.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

_PUZZLE_DIR = Path(__file__).parents[2] / "data" / "puzzles" / "v2"

# ── Types ─────────────────────────────────────────────────────────────────────

class Puzzle(TypedDict):
    id: str
    sphere: str
    thinker_id: str
    thinker_name: str
    level: str           # beginner | intermediate | advanced
    age_range: str
    type: str
    title: str
    hook: str
    challenge: str
    materials: str
    discover: str
    go_deeper: str
    silent_lesson: str

# ── In-memory indexes ─────────────────────────────────────────────────────────

_by_id:     dict[str, Puzzle] = {}
_by_sphere: dict[str, list[Puzzle]] = {}
_by_level:  dict[str, list[Puzzle]] = {}

SPHERES = [
    "philosophy_logic",
    "mathematics",
    "physics",
    "biology_medicine",
    "chemistry",
    "astronomy_cosmology",
    "computer_science_ai",
    "social_sciences",
    "eastern_wisdom",
    "arts_interdisciplinary",
]

LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


def _load():
    for path in sorted(_PUZZLE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            import logging
            logging.getLogger("puzzle.loader").error(f"Failed to load {path}: {e}")
            continue

        sphere = data["sphere"]
        _by_sphere.setdefault(sphere, [])

        for thinker in data.get("thinkers", []):
            for raw in thinker.get("puzzles", []):
                puzzle: Puzzle = {
                    "id":            raw["id"],
                    "sphere":        sphere,
                    "thinker_id":    thinker["id"],
                    "thinker_name":  thinker["name"],
                    "level":         raw["level"],
                    "age_range":     raw.get("age_range", ""),
                    "type":          raw["type"],
                    "title":         raw["title"],
                    "hook":          raw["hook"],
                    "challenge":     raw["challenge"],
                    "materials":     raw.get("materials", ""),
                    "discover":      raw["discover"],
                    "go_deeper":     raw.get("go_deeper", ""),
                    "silent_lesson": raw["silent_lesson"],
                }
                _by_id[puzzle["id"]] = puzzle
                _by_sphere[sphere].append(puzzle)
                _by_level.setdefault(puzzle["level"], []).append(puzzle)


_load()


# ── Public API ────────────────────────────────────────────────────────────────

def get(puzzle_id: str) -> Puzzle | None:
    return _by_id.get(puzzle_id)


def for_sphere(sphere: str) -> list[Puzzle]:
    return _by_sphere.get(sphere, [])


def for_sphere_level(sphere: str, level: str) -> list[Puzzle]:
    return [p for p in _by_sphere.get(sphere, []) if p["level"] == level]


def all_puzzles() -> list[Puzzle]:
    return list(_by_id.values())


def spheres_available() -> list[str]:
    return [s for s in SPHERES if s in _by_sphere]


def concept_keywords(puzzle: Puzzle) -> list[str]:
    """Extract meaningful keywords from silent_lesson for concept mapping."""
    raw = puzzle["silent_lesson"]
    # Split on ; and . and ,
    import re
    parts = re.split(r'[;.,]', raw)
    return [p.strip().lower() for p in parts if len(p.strip()) > 3]
