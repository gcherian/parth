"""Social Preference — group, solo, and teach-back learning signals.

This revives the old dormant agent on its own terms. It is not a duplicate of
psyche.extroversion: it watches for actual collaboration preference in learner
language and keeps a separate, consent-safe state.
"""
from __future__ import annotations

import re
from typing import Any

from kernel.agent import AgentSignals, BaseAgent
from modules.learner_state import psyche as psy

_GROUP = re.compile(
    r"\b(friend|friends|group|team|together|classmate|partner|with someone|"
    r"my class|hum log|saath|dost)\b",
    re.IGNORECASE,
)
_SOLO = re.compile(
    r"\b(alone|by myself|myself|solo|quietly|private|don't show|dont show|"
    r"without anyone|akela|akele)\b",
    re.IGNORECASE,
)
_TEACH = re.compile(
    r"\b(teach|explain to|show my|help my|tell my friend|present|"
    r"samjhaun|samjhana|dikhana)\b",
    re.IGNORECASE,
)


def classify_social_signal(message: str) -> dict[str, float | str]:
    """Return collaboration deltas from one learner message."""
    text = message.strip()
    if not text:
        return {"group": 0.0, "solo": 0.0, "teach_back": 0.0, "marker": "none"}

    group = 1.0 if _GROUP.search(text) else 0.0
    solo = 1.0 if _SOLO.search(text) else 0.0
    teach_back = 1.0 if _TEACH.search(text) else 0.0

    marker = "none"
    if teach_back:
        marker = "teach_back"
    elif group:
        marker = "group"
    elif solo:
        marker = "solo"

    return {
        "group": group,
        "solo": solo,
        "teach_back": teach_back,
        "marker": marker,
    }


def blend_social_state(
    previous: dict[str, Any] | None,
    signal: dict[str, float | str],
) -> dict[str, Any]:
    """EMA update for social learning state."""
    previous = previous or {}
    sample_count = int(previous.get("sample_count", 0) or 0)
    alpha = 0.35 if sample_count < 5 else 0.18

    def blend(key: str, default: float = 0.5) -> float:
        old = float(previous.get(key, default) or default)
        signal_key = key.removesuffix("_preference")
        delta = float(signal.get(signal_key, 0.0) or 0.0)
        target = 0.5 if delta == 0 else 0.85
        return round(old * (1.0 - alpha) + target * alpha, 3)

    return {
        "group_preference": blend("group_preference"),
        "solo_preference": blend("solo_preference"),
        "teach_back_preference": blend("teach_back_preference"),
        "sample_count": sample_count + (0 if signal.get("marker") == "none" else 1),
        "last_signal": str(signal.get("marker", "none")),
    }


class SocialPreferenceAgent(BaseAgent):
    name = "social_preference"
    phase = "both"
    memory_window = "month"

    async def _observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        signal = classify_social_signal(signals.message)
        if signal["marker"] == "none":
            return

        row = await conn.fetchrow(
            """SELECT group_preference, solo_preference, teach_back_preference, sample_count
               FROM learner_state.social_learning_state
               WHERE learner_id=$1""",
            signals.learner_id,
        )
        prior = dict(row) if row else None
        updated = blend_social_state(prior, signal)

        await conn.execute(
            """INSERT INTO learner_state.social_learning_state
               (learner_id, group_preference, solo_preference, teach_back_preference,
                sample_count, last_signal, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,now())
               ON CONFLICT (learner_id) DO UPDATE
               SET group_preference=$2, solo_preference=$3,
                   teach_back_preference=$4, sample_count=$5,
                   last_signal=$6, updated_at=now()""",
            signals.learner_id,
            updated["group_preference"],
            updated["solo_preference"],
            updated["teach_back_preference"],
            updated["sample_count"],
            updated["last_signal"],
        )

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        signal = classify_social_signal(signals.message)
        if signal["marker"] == "teach_back":
            return {"social.teach_back": True}
        if signal["marker"] == "group":
            return {"social.group": True}
        return {}

    async def _read(self, conn, learner_id: str) -> str:
        row = await conn.fetchrow(
            """SELECT group_preference, solo_preference, teach_back_preference, sample_count
               FROM learner_state.social_learning_state
               WHERE learner_id=$1""",
            learner_id,
        )
        psyche = await psy.get_psyche(conn, learner_id)
        ext = psyche.get("extroversion", 0.5)

        if row and (row["sample_count"] or 0) >= 2:
            prefs = {
                "group": row["group_preference"] or 0.5,
                "solo": row["solo_preference"] or 0.5,
                "teach_back": row["teach_back_preference"] or 0.5,
            }
            top = max(prefs, key=prefs.get)
            label = {
                "group": "small-group prompts",
                "solo": "quiet solo thinking",
                "teach_back": "teach-back explanations",
            }[top]
            return f"Social learning: prefers {label} (signal={prefs[top]:.2f})."

        if psyche.get("sample_count", 0) >= 5:
            if ext >= 0.6:
                return f"Social learning: likely benefits from teaching back (extroversion={ext:.2f})."
            if ext <= 0.4:
                return f"Social learning: likely benefits from quiet solo thinking (extroversion={ext:.2f})."
        return ""
