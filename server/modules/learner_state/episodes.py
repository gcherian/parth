"""
Episodic Memory — The moments worth remembering.
=================================================

Not a log. A story.

The interaction log stores everything. Episodic memory stores the moments
that reveal who this child is: when they understood something for the first
time, when they expressed a belief that turned out to be wrong, when they
made a connection no one prompted them to make, when something stopped them
cold with wonder.

Parth uses these to be a mentor, not a search engine.

  "Three weeks ago you said you thought heavier things fall faster.
   Did you ever test that?"

That one sentence does more pedagogical work than ten explanations.

Episode types
-------------
  breakthrough   — "oh I get it", "makes sense now", "acha samjha"
  belief         — stated as confident: "I always thought pi was just 3"
  question       — a deep why-question, > 6 words, genuinely curious
  struggle       — "I can't do this", "makes no sense", expressed difficulty
  connection     — child linked two concepts across domains unprompted
  awe            — "that's crazy", "no way", "how is that possible"

Retrieval strategy (5 episodes per prompt)
-------------------------------------------
  2 most recent            — continuity
  2 most referenced        — what Parth keeps coming back to
  1 oldest open question   — unfinished business; the thread not yet pulled
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal, TypedDict

from foundation.observability import get_logger

log = get_logger("learner.state.episodes")

EpisodeType = Literal["breakthrough", "belief", "question", "struggle", "connection", "awe", "observation"]


class Episode(TypedDict):
    id: str
    learner_id: str
    episode_type: EpisodeType
    verbatim: str            # what the child said, verbatim (≤ 200 chars)
    summary: str             # one-line: "Asked why a googly spins backwards"
    concept_ids: list[str]
    pattern_ids: list[str]
    follow_up: str           # question Parth can use to revisit: "Did you figure it out?"
    referenced_count: int
    last_referenced: str | None
    created_at: str


# ── Detection patterns ───────────────────────────────────────────────────────

_BREAKTHROUGH = re.compile(
    r'\b(oh(h+)?[,!.]?\s*(i\s+)?(get|see|understand|know)|makes?\s+sense|'
    r'got\s+it|now\s+i\s+(get|see|understand)|acha(\s+samjha)?|'
    r'samajh\s+(gaya|gayi|aaya)|finally|that\'?s?\s+(why|how|what)|'
    r'so\s+that\'?s?\s+(why|how))\b',
    re.IGNORECASE
)

_AWE = re.compile(
    r'\b(wow|whoa|that\'?s?\s+(crazy|insane|wild|amazing|unbelievable|mind.?blowing)|'
    r'no\s+way|can\'?t\s+believe|how\s+is\s+that\s+(possible|real)|'
    r'that\s+can\'?t\s+be|seriously\?|yaar\s+kya|bahut\s+(badi|bada)|'
    r'impossible|incredible)\b',
    re.IGNORECASE
)

_BELIEF = re.compile(
    r'\b(i\s+(always|used\s+to|never)?\s*(thought|believed|assumed|knew)|'
    r'isn\'?t\s+it\s+(because|that|just)|i\s+thought\s+it\s+was|'
    r'mujhe\s+lagta\s+tha|main\s+sochta\s+tha)\b',
    re.IGNORECASE
)

_STRUGGLE = re.compile(
    r'\b(i\s+can\'?t|can\'?t\s+do|don\'?t\s+understand|don\'?t\s+get|'
    r'makes?\s+no\s+sense|too\s+hard|i\s+give\s+up|never\s+(get|understand)|'
    r'confused|lost|nahi\s+aata|samajh\s+nahi|bahut\s+mushkil)\b',
    re.IGNORECASE
)

_CONNECTION = re.compile(
    r'\b(same\s+as|like\s+when|similar\s+to|is\s+(this|that)\s+(like|the\s+same)|'
    r'related\s+to|so\s+(that\'?s?\s+why|this\s+is\s+why)|'
    r'ohh?\s+so\s+(this|that|it)|waisa\s+hi|matlab\s+wahi)\b',
    re.IGNORECASE
)

_DEEP_QUESTION = re.compile(
    r'^.{20,}(\?|\.\.\.)\s*$',   # long message ending in question mark or trailing dots
    re.IGNORECASE
)

_WHY_QUESTION = re.compile(
    r'\b(why|how\s+does|how\s+do|how\s+come|what\s+makes|what\s+causes|'
    r'kyun|kyunki|kaise\s+kaam|kaise\s+hota)\b',
    re.IGNORECASE
)


def detect_type(message: str) -> EpisodeType | None:
    """Return the episode type if this message is worth storing, else None."""
    text = message.strip()
    if len(text) < 5:
        return None

    if _BREAKTHROUGH.search(text):
        return "breakthrough"
    if _AWE.search(text):
        return "awe"
    if _CONNECTION.search(text):
        return "connection"
    if _BELIEF.search(text):
        return "belief"
    if _STRUGGLE.search(text):
        return "struggle"
    # Deep question: has a why-word AND is more than 6 words
    if _WHY_QUESTION.search(text) and len(text.split()) >= 6:
        return "question"

    return None


def _summarise(episode_type: EpisodeType, verbatim: str, concepts: list[str]) -> str:
    """Build a compact one-line summary Parth can use to reference this episode."""
    concept_hint = f" [{', '.join(concepts[:2])}]" if concepts else ""
    short = verbatim[:80].rstrip()
    if len(verbatim) > 80:
        short += "…"

    prefixes = {
        "breakthrough": "Understood",
        "belief":       "Believed",
        "question":     "Asked",
        "struggle":     "Struggled with",
        "connection":   "Connected",
        "awe":          "Amazed by",
        "observation":  "Noticed",
    }
    return f'{prefixes[episode_type]}: "{short}"{concept_hint}'


def _follow_up(episode_type: EpisodeType, verbatim: str) -> str:
    """Generate a follow-up question Parth can use to revisit this episode."""
    if episode_type == "question":
        return "Did you find an answer to that? What do you think now?"
    if episode_type == "belief":
        return "You mentioned you used to think that — has your view changed?"
    if episode_type == "struggle":
        return "Last time this felt hard — does it feel any different now?"
    if episode_type == "breakthrough":
        return "You got it that day — can you explain it to me in your own words?"
    if episode_type == "connection":
        return "You noticed that connection — have you spotted it anywhere else?"
    if episode_type == "awe":
        return "That surprised you — has anything else surprised you like that since?"
    return ""


# ── DB operations ─────────────────────────────────────────────────────────────

async def store(
    conn,
    learner_id: str,
    episode_type: EpisodeType,
    verbatim: str,
    concepts: list[str],
    patterns: list[str],
) -> Episode:
    summary   = _summarise(episode_type, verbatim, concepts)
    follow_up = _follow_up(episode_type, verbatim)
    episode_id = str(uuid.uuid4())

    await conn.execute(
        """
        INSERT INTO learner_state.episodes
            (id, learner_id, episode_type, verbatim, summary,
             concept_ids, pattern_ids, follow_up)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        """,
        episode_id, learner_id, episode_type,
        verbatim[:200], summary, concepts, patterns, follow_up,
    )
    log.info("episode_stored", learner_id=learner_id, type=episode_type,
             summary=summary[:60])

    return Episode(
        id=episode_id, learner_id=learner_id, episode_type=episode_type,
        verbatim=verbatim[:200], summary=summary, concept_ids=concepts,
        pattern_ids=patterns, follow_up=follow_up,
        referenced_count=0, last_referenced=None,
        created_at=datetime.utcnow().isoformat(),
    )


async def load_for_prompt(conn, learner_id: str) -> list[dict]:
    """
    Return up to 5 episodes for prompt injection:
      2 most recent, 2 most referenced, 1 oldest unanswered question.
    Deduplicates by id.
    """
    recent = await conn.fetch(
        """
        SELECT id, episode_type, verbatim, summary, follow_up,
               referenced_count, last_referenced, created_at
        FROM learner_state.episodes
        WHERE learner_id = $1
        ORDER BY created_at DESC
        LIMIT 2
        """,
        learner_id,
    )

    popular = await conn.fetch(
        """
        SELECT id, episode_type, verbatim, summary, follow_up,
               referenced_count, last_referenced, created_at
        FROM learner_state.episodes
        WHERE learner_id = $1 AND referenced_count > 0
        ORDER BY referenced_count DESC
        LIMIT 2
        """,
        learner_id,
    )

    # Oldest unresolved question — one the child hasn't heard back about recently
    open_q = await conn.fetch(
        """
        SELECT id, episode_type, verbatim, summary, follow_up,
               referenced_count, last_referenced, created_at
        FROM learner_state.episodes
        WHERE learner_id = $1
          AND episode_type IN ('question', 'belief')
          AND (last_referenced IS NULL OR last_referenced < now() - interval '7 days')
        ORDER BY created_at ASC
        LIMIT 1
        """,
        learner_id,
    )

    seen, result = set(), []
    for row in list(recent) + list(popular) + list(open_q):
        if row["id"] not in seen:
            seen.add(row["id"])
            result.append(dict(row))

    return result[:5]


async def mark_referenced(conn, episode_id: str) -> None:
    await conn.execute(
        """
        UPDATE learner_state.episodes
        SET referenced_count = referenced_count + 1,
            last_referenced  = now()
        WHERE id = $1
        """,
        episode_id,
    )


async def get_patterns_for_message(conn, concept_ids: list[str]) -> list[str]:
    """Look up which patterns are associated with these concepts."""
    if not concept_ids:
        return []
    rows = await conn.fetch(
        "SELECT DISTINCT unnest(patterns) as p FROM curriculum_graph.concepts WHERE id = ANY($1)",
        concept_ids,
    )
    return [r["p"] for r in rows]


# ── Context injection ─────────────────────────────────────────────────────────

def build_episode_context(episodes: list[dict]) -> str:
    """
    Builds the episodic memory block for Parth's system prompt.
    Parth can reference any of these naturally in conversation.
    """
    if not episodes:
        return ""

    lines = ["Episodes worth remembering about this child:"]
    for ep in episodes:
        age  = _age_label(ep["created_at"])
        line = f"  • [{ep['episode_type'].upper()}, {age}] {ep['summary']}"
        if ep.get("follow_up") and ep.get("referenced_count", 0) == 0:
            line += f"\n    ↳ Follow-up available: \"{ep['follow_up']}\""
        lines.append(line)

    lines.append(
        "You may reference these naturally — not as a list, but as a mentor who remembers."
    )
    return "\n".join(lines)


def _age_label(created_at_iso: str | None) -> str:
    if not created_at_iso:
        return "recently"
    try:
        dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        delta = datetime.utcnow() - dt.replace(tzinfo=None)
        days = delta.days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days} days ago"
        if days < 30:
            return f"{days // 7} week{'s' if days >= 14 else ''} ago"
        return f"{days // 30} month{'s' if days >= 60 else ''} ago"
    except Exception:
        return "recently"
