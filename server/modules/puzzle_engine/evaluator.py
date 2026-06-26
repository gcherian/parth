"""
Puzzle Response Evaluator
=========================

Scores a child's response to a V2 puzzle on two axes:

1. Quality (0–3):
   0 = blank / gave up
   1 = attempted but significant gaps
   2 = reached the "discover" insight (the goal)
   3 = attempted go_deeper independently

2. Error response classification:
   growth | fixed | avoidant | perfectionist | unknown

Both are scored by a fast LLM call using the puzzle's `discover` text
as the ground-truth insight. The evaluator is called asynchronously
so it never delays the child's next puzzle.
"""
from __future__ import annotations

import json
import logging

import httpx

from config import Config
from modules.puzzle_engine.error_response import classify_error_response

log = logging.getLogger("puzzle.evaluator")

_PROMPT = """\
You are evaluating a child's response to a hands-on learning puzzle.

PUZZLE TITLE: {title}
EXPECTED INSIGHT: {discover}

CHILD'S RESPONSE: "{response}"
TIME SPENT (seconds): {time_seconds}

Score the response and reply in JSON only:
{{
  "quality": 0 to 3,
  "quality_reason": "one sentence",
  "reached_insight": true or false,
  "attempted_deeper": true or false,
  "misconception": "one sentence describing a wrong belief, or empty string",
  "concepts_demonstrated": ["list", "of", "concepts", "shown", "correctly"]
}}

Quality scale:
  0 = no attempt or complete mismatch
  1 = genuine attempt, missing the key insight
  2 = reached the core insight (matches discover text)
  3 = went beyond the insight, showed deeper understanding or connection

Be generous with partial credit. A child who makes a genuine attempt scores at least 1.
"""


async def evaluate_response(
    puzzle: dict,
    child_response: str,
    time_seconds: int = 0,
) -> dict:
    """
    Returns:
      quality: int (0-3)
      reached_insight: bool
      attempted_deeper: bool
      misconception: str
      concepts_demonstrated: list[str]
      error_response_type: str
    """
    default = {
        "quality": 1 if child_response.strip() else 0,
        "quality_reason": "Evaluated locally (LLM unavailable)",
        "reached_insight": False,
        "attempted_deeper": False,
        "misconception": "",
        "concepts_demonstrated": [],
        "error_response_type": classify_error_response(child_response),
    }

    if not child_response.strip():
        default["quality"] = 0
        default["error_response_type"] = "avoidant"
        return default

    try:
        prompt = _PROMPT.format(
            title=puzzle.get("title", ""),
            discover=puzzle.get("discover", "")[:400],
            response=child_response[:500],
            time_seconds=time_seconds,
        )
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={
                    "model": Config.FAST_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            r.raise_for_status()
            raw = json.loads(r.json().get("response", "{}"))

        return {
            "quality":              int(raw.get("quality", 1)),
            "quality_reason":       str(raw.get("quality_reason", "")),
            "reached_insight":      bool(raw.get("reached_insight", False)),
            "attempted_deeper":     bool(raw.get("attempted_deeper", False)),
            "misconception":        str(raw.get("misconception", "") or ""),
            "concepts_demonstrated": list(raw.get("concepts_demonstrated", [])),
            "error_response_type":  classify_error_response(child_response),
        }

    except Exception as e:
        log.debug(f"Puzzle evaluator LLM call failed: {e}")
        return default
