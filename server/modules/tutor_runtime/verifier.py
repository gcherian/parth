"""
Math response verifier — catches numerical/arithmetic errors before delivery.
Uses the fast model (llama3.2) for speed. Only fires when the response contains
numbers or equations. Single retry if flagged.
"""
import json
import re

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("tutor_runtime.verifier")

# Detect responses that contain math content worth checking
_MATH_SIGNAL = re.compile(
    r'[\d]+[\s]*([\+\-\×\÷\*\/\=]|divided by|multiplied|squared|equals)[\s]*[\d]|= [\d]',
    re.IGNORECASE,
)

_VERIFIER_PROMPT = """You are a math fact-checker. A tutor gave this response to a student.
Check ONLY for mathematical errors (wrong calculations, wrong formulas, wrong numbers).
Ignore teaching style, simplifications, or pedagogy.

Tutor response:
{response}

Reply with JSON only:
{{"correct": true/false, "error": "describe the math error if any, else empty string"}}"""


async def verify_math(response_text: str, fast_model: str) -> tuple[bool, str]:
    """
    Returns (is_correct, error_description).
    If no math content is detected, returns (True, '') without calling the model.
    Fails open — any exception returns (True, '') so the child is never blocked.
    """
    if not _MATH_SIGNAL.search(response_text):
        return True, ''

    prompt = _VERIFIER_PROMPT.format(response=response_text[:800])
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={
                    "model": fast_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0},
                },
            )
            r.raise_for_status()
        raw = r.json().get("response", "")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("correct", True), data.get("error", "")
    except Exception as exc:
        log.warning("verifier_failed", error=str(exc))

    return True, ''  # fail open — don't block on verifier error
