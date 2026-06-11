"""Language Bridge — code-mesh policy; bilingual glossary gaps.

Ref: García and Lin, "Translanguaging in Bilingual Education" —
learners draw from a unified linguistic repertoire; never punish code-switching.
"""
from __future__ import annotations
from typing import Any
from kernel.agent import LearnerAgent, AgentSignals
from modules.learner_state import profile as prof


def _lang_label(ratio: float) -> str:
    if ratio < 0.4:
        return "hindi"
    if ratio < 0.7:
        return "mixed"
    return "english"


_POLICY = {
    "hindi":   "Explain in Hindi/Hinglish; key terms in both scripts.",
    "mixed":   "Mix freely; match the child's code-switching rhythm.",
    "english": "English-dominant; occasional Hindi terms welcome.",
}


class LanguageBridgeAgent(LearnerAgent):
    name = "language_bridge"
    phase = "both"
    memory_window = "permanent"

    async def observe(self, signals: AgentSignals, conn) -> None:
        if signals.phase != "post":
            return
        try:
            await prof.update_language(conn, signals.learner_id, signals.language_ratio)
            await conn.execute(
                """INSERT INTO learner_state.language_state
                   (learner_id, preferred_lang, language_ratio, updated_at)
                   VALUES ($1,$2,$3,now())
                   ON CONFLICT (learner_id) DO UPDATE
                   SET preferred_lang=$2, language_ratio=$3, updated_at=now()""",
                signals.learner_id,
                _lang_label(signals.language_ratio),
                signals.language_ratio,
            )
        except Exception:
            pass

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {"lang.preference": _lang_label(signals.language_ratio)}

    async def read(self, conn, learner_id: str) -> str:
        try:
            row = await conn.fetchrow(
                "SELECT preferred_lang, language_ratio FROM learner_state.language_state WHERE learner_id=$1",
                learner_id,
            )
            if not row:
                p = await conn.fetchrow(
                    "SELECT language_ratio FROM learner_state.profiles WHERE learner_id=$1", learner_id
                )
                if not p:
                    return ""
                ratio = p["language_ratio"] or 1.0
                lang  = _lang_label(ratio)
            else:
                lang  = row["preferred_lang"]
                ratio = row["language_ratio"]
            policy = _POLICY.get(lang, "Match child's language.")
            return f"Language: {lang} (ratio={ratio:.2f}). {policy}"
        except Exception:
            return ""
