"""
LLM-based signal evaluator — one call per interaction, runs in post-processing.
Returns: misconception, misconception_concept, emotion, engagement.
"""
import json
import re

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("tutor_runtime.evaluator")

_PROMPT = """\
You are an expert education analyst. Read this student's message and respond with ONLY a JSON object.

Student message: {question}
Heuristic emotion hint: {emotion_hint}

Respond with valid JSON only, no explanation:
{{
  "has_misconception": true or false,
  "misconception": "brief description or empty string",
  "misconception_concept": "concept_id from this list or empty: photosynthesis, cell_biology, fractions, algebra_basics, newton_laws, water_cycle, mughal_empire, indian_independence, arithmetic, geometry, electricity, human_body, ecosystem, magnetism, light_optics, sound, periodic_table, bodmas, decimals, ratios",
  "emotion": "one of: frustrated, distressed, anxious, confused, curious, excited, disengaged, neutral",
  "engagement": integer from 1 to 10
}}

Emotion guide: use 'frustrated' for struggle/give-up language, 'distressed' for panic/fear,
'anxious' for exam worry, 'confused' for genuine not-understanding, 'curious' for exploring,
'excited' for delight, 'disengaged' for boredom/dismissal, 'neutral' for factual questions."""


async def evaluate(question: str, emotion_hint: str = "neutral") -> dict:
    prompt = _PROMPT.format(question=question[:500], emotion_hint=emotion_hint)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={
                    "model": Config.FAST_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            r.raise_for_status()
        raw = r.json().get("response", "")
        # Extract JSON from response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "misconception": data.get("misconception", "") if data.get("has_misconception") else "",
                "misconception_concept": data.get("misconception_concept", ""),
                "emotion": data.get("emotion", emotion_hint),
                "engagement": int(data.get("engagement", 5)),
            }
    except Exception as e:
        log.warning("evaluator_failed", error=str(e))

    return {
        "misconception": "",
        "misconception_concept": "",
        "emotion": emotion_hint,
        "engagement": 5,
    }
