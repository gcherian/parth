"""
Enhanced evaluator — single background LLM call returns:
  misconception, emotion, engagement score, and concept links.
"""
import json
import logging

import httpx

from config import Config

log = logging.getLogger("parth.eval")

_PROMPT = """You are analysing a student's message to a tutoring AI.

Student message: "{question}"

Reply in JSON only, no other text:
{{
  "has_misconception": true or false,
  "misconception": "one sentence describing the wrong belief, or empty string",
  "misconception_concept": "one word concept id from: photosynthesis nutrition_plants nutrition_animals cell motion force light electricity combustion matter fractions integers algebra geometry mensuration french_revolution nationalism geography_india water_cycle ecosystem, or empty string",
  "emotion": "one of: curious confused frustrated excited neutral disengaged",
  "engagement": integer 1 to 10
}}"""


async def evaluate(question: str, emotion_hint: str = "neutral") -> dict:
    """
    Returns dict with keys:
      misconception: str
      misconception_concept: str
      emotion: str
      engagement: int
    """
    default = {
        "misconception": "",
        "misconception_concept": "",
        "emotion": emotion_hint,
        "engagement": 5,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={
                    "model": Config.FAST_MODEL,
                    "prompt": _PROMPT.format(question=question[:400]),
                    "stream": False,
                    "format": "json",
                },
            )
            r.raise_for_status()
            raw = r.json().get("response", "{}")
            result = json.loads(raw)
            return {
                "misconception": str(result.get("misconception", "") or "").strip(),
                "misconception_concept": str(result.get("misconception_concept", "") or "").strip(),
                "emotion": str(result.get("emotion", emotion_hint) or emotion_hint),
                "engagement": int(result.get("engagement", 5) or 5),
            }
    except Exception as e:
        log.debug(f"Evaluator skipped: {e}")
        return default
