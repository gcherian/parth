"""
Open-Loop Generator — The question that brings them back.
=========================================================

Not a notification. Not a homework assignment.
A planted seed.

At the right moment, Parth leaves the child with something unresolved — a
question calibrated to what they just understood, just struggled with, or
just found amazing. Not for them to look up. For them to carry.

The Zeigarnik effect: unfinished things stay in mind. A child who is
wondering about something will come back to resolve it. Not because an
app sent them a push notification, but because the question is alive in them.

Parth references the open loop naturally next session:
  "Last time you were wondering about why a spinning top doesn't fall.
   Did you figure it out?"

The child never knows the system planted it. They just feel understood.

Loop lifecycle
--------------
  generated → open (injected for up to 7 days)
  open      → closed (when child returns to the topic)
  open      → expired (after 7 days, quietly retired)

Generation priority
-------------------
  1. From the most recent 'question' episode — deepening their own question
  2. From the dominant curiosity thread — extending what's already live
  3. From the most recent 'breakthrough' episode — making mastery real
  4. From concept context — generic but grounded wonder
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import TypedDict

from foundation.observability import get_logger

log = get_logger("learner.state.open_loops")


class OpenLoop(TypedDict):
    id: str
    learner_id: str
    question: str
    concept_ids: list[str]
    status: str          # 'open' | 'closed' | 'expired'
    created_at: str
    closed_at: str | None


# ── Wonder templates by episode type ─────────────────────────────────────────

_BY_TYPE: dict[str, list[str]] = {
    "breakthrough": [
        "You got it today. Here's the harder test: can you explain it to someone at home using a completely different example than I gave?",
        "You understand this now. Here's the question to sit with: where does it break down? When would this NOT work?",
        "You got this. What was the exact moment it clicked? Can you name it?",
    ],
    "question": [
        "You asked that — I want you to sit with it overnight. Don't look it up. What's your best guess?",
        "That's a great question. Before I answer it next time, what do you think the answer might be?",
        "That question has a surprising answer. Think about it tonight and come back with your theory.",
    ],
    "awe": [
        "That surprised you. Here's something even more surprising connected to it — see if you can figure out what.",
        "That's astonishing, isn't it? Tonight: why do you think it works that way? What would have to be true?",
        "You were amazed by that. Find one more thing today that surprises you the same way.",
    ],
    "struggle": [
        "It felt hard today. Tonight, just try to say in one sentence what made it confusing — nothing more.",
        "You found this tricky. That's actually a clue. What specifically made it stick? Just notice it.",
    ],
    "connection": [
        "You spotted that connection. Here's the challenge: find one more — in a completely different domain.",
        "You noticed those two things are related. What's the third thing they both connect to?",
    ],
    "belief": [
        "You used to think that. Has your thinking fully shifted? When did you first start believing it?",
        "Beliefs like that are interesting — where do you think it came from?",
    ],
}

# Generic wonders when no episode is available
_GENERIC: list[str] = [
    "Tonight: find this happening somewhere in your own life. Don't look it up — just observe.",
    "Tonight, try explaining what we talked about to someone in your family using your own example, not mine.",
    "Here's a question to sleep on: where does this pattern show up somewhere completely unexpected?",
    "What would the world look like if this worked differently? Just imagine it.",
    "This connects to something bigger. Tonight, see if you can guess what that bigger thing might be.",
    "You learned something new today. The real test: can you teach it to someone else by tomorrow?",
]


# ── Generation ────────────────────────────────────────────────────────────────

def generate(
    concepts: list[str],
    episodes: list[dict],
    threads: list[dict],
) -> tuple[str, list[str]] | tuple[None, None]:
    """
    Returns (question_text, concept_ids) or (None, None) if nothing to plant.

    Priority:
      1. Most recent 'question' or 'awe' episode → from its follow_up
      2. Most recent 'breakthrough' episode → deepen it
      3. Dominant curiosity thread → extend it
      4. Generic concept-based wonder
    """
    # Priority 1: question or awe episode → use its follow_up or a type template
    for ep in reversed(episodes):
        if ep.get("episode_type") in ("question", "awe"):
            follow_up = ep.get("follow_up", "")
            if follow_up:
                return follow_up, ep.get("concept_ids", concepts[:1])
            tpl = random.choice(_BY_TYPE.get(ep["episode_type"], _GENERIC))
            return tpl, ep.get("concept_ids", concepts[:1])

    # Priority 2: breakthrough episode
    for ep in reversed(episodes):
        if ep.get("episode_type") == "breakthrough":
            tpl = random.choice(_BY_TYPE["breakthrough"])
            return tpl, ep.get("concept_ids", concepts[:1])

    # Priority 3: dominant curiosity thread
    if threads:
        hot = max(threads, key=lambda t: t.get("heat", 0))
        if hot.get("heat", 0) >= 0.20:
            seed = hot.get("seed_question", "")[:100]
            if seed:
                return (
                    f"You were wondering: \"{seed}\". Don't look it up — what's your best guess?",
                    concepts[:1],
                )

    # Priority 4: generic concept wonder
    if not concepts:
        return None, None

    tpl = random.choice(_GENERIC)
    return tpl, concepts[:1]


def should_generate(total_questions: int, episode_type: str | None) -> bool:
    """
    Fire a new open loop when:
      - A meaningful episode was detected (question/awe/breakthrough/belief), OR
      - Every 5th interaction (steady cadence — keeps loops fresh even in quiet sessions)
    """
    if episode_type in ("question", "awe", "breakthrough", "belief", "connection"):
        return True
    return total_questions > 0 and total_questions % 5 == 0


# ── DB operations ─────────────────────────────────────────────────────────────

async def store(
    conn,
    learner_id: str,
    question: str,
    concept_ids: list[str],
) -> OpenLoop:
    loop_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO learner_state.open_loops
            (id, learner_id, question, concept_ids, status)
        VALUES ($1, $2, $3, $4, 'open')
        """,
        loop_id, learner_id, question, concept_ids,
    )
    log.info("open_loop_stored", learner_id=learner_id,
             question=question[:60])
    return OpenLoop(
        id=loop_id, learner_id=learner_id, question=question,
        concept_ids=concept_ids, status="open",
        created_at=datetime.utcnow().isoformat(), closed_at=None,
    )


async def load_open(conn, learner_id: str) -> list[dict]:
    """Load open loops from the last 7 days."""
    rows = await conn.fetch(
        """
        SELECT id, question, concept_ids, status, created_at
        FROM learner_state.open_loops
        WHERE learner_id = $1
          AND status = 'open'
          AND created_at > now() - interval '7 days'
        ORDER BY created_at DESC
        LIMIT 3
        """,
        learner_id,
    )
    return [dict(r) for r in rows]


async def expire_old(conn, learner_id: str) -> None:
    """Retire loops older than 7 days."""
    await conn.execute(
        """
        UPDATE learner_state.open_loops
        SET status = 'expired'
        WHERE learner_id = $1
          AND status = 'open'
          AND created_at < now() - interval '7 days'
        """,
        learner_id,
    )


async def close(conn, loop_id: str) -> None:
    await conn.execute(
        """
        UPDATE learner_state.open_loops
        SET status = 'closed', closed_at = now()
        WHERE id = $1
        """,
        loop_id,
    )


# ── Context injection ─────────────────────────────────────────────────────────

def build_context(loops: list[dict]) -> str:
    """
    Returns the open-loop block for Parth's system prompt.
    Parth can reference these naturally — not as a checklist, as a mentor
    who remembers what they left unfinished.
    """
    if not loops:
        return ""

    lines = ["Open wonder(s) you left this child with:"]
    for loop in loops[:2]:
        age = _age_label(loop.get("created_at"))
        lines.append(f"  • [{age}] \"{loop['question']}\"")

    lines.append(
        "If they bring up the topic or you see a natural opening, ask if they thought about it. "
        "Don't force it — let it arise."
    )
    return "\n".join(lines)


def _age_label(created_at_iso) -> str:
    if not created_at_iso:
        return "recently"
    try:
        if hasattr(created_at_iso, "isoformat"):
            dt = created_at_iso.replace(tzinfo=None)
        else:
            dt = datetime.fromisoformat(str(created_at_iso).replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
        delta = datetime.utcnow() - dt
        days = delta.days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days} days ago"
        return f"{days // 7} week{'s' if days >= 14 else ''} ago"
    except Exception:
        return "recently"
