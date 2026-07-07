"""Value & Purpose reflection support.

Value/purpose does not fit the per-message agent pattern. The MVP path is a
periodic reflective prompt, then a lightweight synthesis pass. This module uses
deterministic theme extraction now and leaves room for an LLM-backed pass later.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


REFLECTION_PROMPTS: list[dict[str, str]] = [
    {
        "id": "why_learn_now",
        "text": "What is one thing you want learning to help you do in real life?",
    },
    {
        "id": "proud_future",
        "text": "If you became really good at something this year, what would make you proud?",
    },
    {
        "id": "help_someone",
        "text": "Who would you like to help with what you learn, and how?",
    },
    {
        "id": "world_question",
        "text": "What problem in the world do you wish you understood better?",
    },
]

_THEME_KEYWORDS: dict[str, set[str]] = {
    "family": {"family", "parents", "mother", "father", "mom", "dad", "ghar", "home"},
    "helping": {"help", "support", "teach", "share", "care", "seva"},
    "building": {"build", "make", "create", "invent", "app", "robot", "design"},
    "discovery": {"why", "discover", "understand", "explore", "question", "mystery"},
    "beauty": {"art", "music", "beautiful", "draw", "story", "poem", "creative"},
    "justice": {"fair", "justice", "equal", "rights", "safe", "bully"},
    "nature": {"nature", "animal", "plant", "climate", "space", "earth"},
    "mastery": {"good", "better", "win", "exam", "marks", "rank", "practice"},
    "career": {"doctor", "engineer", "scientist", "teacher", "job", "career"},
    "community": {"village", "city", "school", "people", "country", "india"},
}


def extract_value_themes(text: str) -> dict[str, float]:
    """Return normalized value/purpose themes from a reflection response."""
    lower = text.lower()
    raw: dict[str, float] = {}
    for theme, words in _THEME_KEYWORDS.items():
        hits = sum(1 for word in words if word in lower)
        if hits:
            raw[theme] = float(hits)

    if not raw:
        return {}
    total = sum(raw.values())
    return {theme: round(score / total, 3) for theme, score in raw.items()}


def merge_theme_state(previous: dict[str, Any] | None, new_themes: dict[str, float]) -> dict[str, Any]:
    previous = previous or {}
    old_themes = previous.get("purpose_themes") or {}
    if isinstance(old_themes, str):
        old_themes = {}
    alpha = 0.45 if not old_themes else 0.25
    merged: dict[str, float] = {}
    for theme in set(old_themes) | set(new_themes):
        merged[theme] = round(float(old_themes.get(theme, 0.0)) * (1 - alpha) + float(new_themes.get(theme, 0.0)) * alpha, 3)
    merged = {k: v for k, v in sorted(merged.items(), key=lambda item: item[1], reverse=True) if v >= 0.03}
    sample_count = int(previous.get("sample_count", 0) or 0) + 1
    confidence = min(1.0, 0.25 + sample_count * 0.18 + min(len(merged), 4) * 0.05)
    return {
        "purpose_themes": merged,
        "values": list(merged.keys())[:4],
        "confidence": round(confidence, 3),
        "sample_count": sample_count,
    }


async def next_reflection_prompt(conn, learner_id: str) -> dict[str, Any]:
    """Choose the next prompt, rotating away from the most recent one."""
    row = await conn.fetchrow(
        """SELECT prompt_id
           FROM learner_state.value_purpose_reflections
           WHERE learner_id=$1
           ORDER BY created_at DESC
           LIMIT 1""",
        learner_id,
    )
    last_id = row["prompt_id"] if row else ""
    prompt = next((p for p in REFLECTION_PROMPTS if p["id"] != last_id), REFLECTION_PROMPTS[0])
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM learner_state.value_purpose_reflections WHERE learner_id=$1",
        learner_id,
    ) or 0
    return {
        "learner_id": learner_id,
        "prompt": prompt,
        "reflection_count": int(count),
        "cadence": "monthly_or_after_8_sessions",
    }


async def record_reflection(
    conn,
    learner_id: str,
    prompt_id: str,
    prompt_text: str,
    response_text: str,
) -> dict[str, Any]:
    """Persist one reflection and update the purpose state."""
    themes = extract_value_themes(response_text)
    reflection_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO learner_state.value_purpose_reflections
           (id, learner_id, prompt_id, prompt_text, response_text, themes_json, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,now())""",
        reflection_id,
        learner_id,
        prompt_id,
        prompt_text[:500],
        response_text[:2000],
        themes,
    )

    row = await conn.fetchrow(
        """SELECT purpose_themes, values_json, confidence, sample_count
           FROM learner_state.value_purpose_state
           WHERE learner_id=$1""",
        learner_id,
    )
    previous = dict(row) if row else None
    state = merge_theme_state(previous, themes)

    await conn.execute(
        """INSERT INTO learner_state.value_purpose_state
           (learner_id, purpose_themes, values_json, confidence, sample_count, updated_at)
           VALUES ($1,$2,$3,$4,$5,now())
           ON CONFLICT (learner_id) DO UPDATE
           SET purpose_themes=$2, values_json=$3, confidence=$4,
               sample_count=$5, updated_at=now()""",
        learner_id,
        state["purpose_themes"],
        state["values"],
        state["confidence"],
        state["sample_count"],
    )
    return {
        "reflection_id": reflection_id,
        "learner_id": learner_id,
        "themes": themes,
        "state": state,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


async def load_value_purpose(conn, learner_id: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        """SELECT purpose_themes, values_json, confidence, sample_count, updated_at
           FROM learner_state.value_purpose_state
           WHERE learner_id=$1""",
        learner_id,
    )
    if not row:
        return {
            "purpose_themes": {},
            "values": [],
            "confidence": 0.0,
            "sample_count": 0,
            "updated_at": None,
        }
    return {
        "purpose_themes": row["purpose_themes"] or {},
        "values": row["values_json"] or [],
        "confidence": float(row["confidence"] or 0.0),
        "sample_count": int(row["sample_count"] or 0),
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
