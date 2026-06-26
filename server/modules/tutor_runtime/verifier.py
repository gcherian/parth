"""
Math response verifier — catches numerical/arithmetic errors before delivery.

Uses the fast Ollama model locally, or Anthropic when running in cloud mode.
Only fires when the response contains numbers or equations. Fails open.
"""
import json
import re

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("tutor_runtime.verifier")

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


async def verify_math(response_text: str, ollama_model: str | None) -> tuple[bool, str]:
    """
    Returns (is_correct, error_description).
    If no math content is detected, returns (True, '') without calling the model.
    Fails open — any exception returns (True, '') so the child is never blocked.

    ollama_model: pass None to force Anthropic path (used when TUTOR_BACKEND=anthropic).
    """
    if not _MATH_SIGNAL.search(response_text):
        return True, ''

    prompt = _VERIFIER_PROMPT.format(response=response_text[:800])

    # Use Anthropic when in cloud mode (no Ollama available or not requested)
    if ollama_model is None or Config.use_anthropic_tutor():
        return await _verify_with_anthropic(prompt)
    return await _verify_with_ollama(prompt, ollama_model)


async def _verify_with_ollama(prompt: str, model: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.0}},
            )
            r.raise_for_status()
        raw = r.json().get("response", "")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("correct", True), data.get("error", "")
    except Exception as exc:
        log.warning("verifier_ollama_failed", error=str(exc))
    return True, ''


async def _verify_with_anthropic(prompt: str) -> tuple[bool, str]:
    if not Config.ANTHROPIC_API_KEY:
        return True, ''
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         Config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":       Config.TUTOR_MODEL,
                    "max_tokens":  128,
                    "temperature": 0.0,
                    "messages":    [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("correct", True), data.get("error", "")
    except Exception as exc:
        log.warning("verifier_anthropic_failed", error=str(exc))
    return True, ''
