"""
Curiosity Tracker — What is this child wondering about RIGHT NOW?
=================================================================

Session-scoped. Resets each day. Never accumulates into a permanent profile.

A curiosity thread is born when a child asks a question that reveals they want
to understand something — not just get an answer. It grows when they return to
the same territory unprompted. It carries heat that decays if ignored.

What Parth receives:
  "Dominant curiosity: why does a googly spin backwards [→ angular momentum].
   Returned to this 2 times. Heat: high. Follow this thread if opportunity arises."

The child never knows this is happening. They just feel heard.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, date
from typing import TypedDict

from foundation.observability import get_logger

log = get_logger("learner.state.curiosity")

# ── Curiosity signal patterns ────────────────────────────────────────────────

# WHY — the child wants to understand mechanism, not just fact
_WHY = re.compile(
    r'\b(why|how does|how do|how come|what makes|what causes|kyun|kyunki|kaise kaam)\b',
    re.IGNORECASE
)

# PUSHBACK — the child isn't satisfied with the answer
_PUSHBACK = re.compile(
    r'\b(but|wait|that can\'?t|that doesn\'?t|i thought|are you sure|really\?|'
    r'lekin|par|matlab|toh phir)\b',
    re.IGNORECASE
)

# SPECULATION — the child is generating hypotheses
_SPECULATE = re.compile(
    r'\b(what if|could it be|maybe|is it because|would that mean|'
    r'kya agar|shayad|toh kya)\b',
    re.IGNORECASE
)

# CONNECTION — the child is linking concepts across domains
_CONNECT = re.compile(
    r'\b(same as|like when|similar to|is that why|related to|'
    r'matlab wahi|waisa hi)\b',
    re.IGNORECASE
)

# RETURN — short message that shows they're still thinking about prior topic
_CONTINUATION = re.compile(
    r'^(and|also|so|but then|what about|one more|okay but|'
    r'aur|toh|lekin phir)\b',
    re.IGNORECASE
)

_HEAT_DECAY = 0.75      # per message without signal
_HEAT_WHY = 0.35
_HEAT_PUSHBACK = 0.30
_HEAT_SPECULATE = 0.25
_HEAT_CONNECT = 0.20
_HEAT_RETURN = 0.40     # strongest signal — they came back to it


class CuriositySignal(TypedDict):
    type: str          # 'why' | 'pushback' | 'speculate' | 'connect' | 'return' | 'none'
    heat_delta: float
    keywords: list[str]


class Thread(TypedDict):
    thread_id: str
    seed_question: str
    keywords: list[str]
    heat: float
    times_returned: int
    first_seen: str
    last_seen: str


# ── Signal detection ─────────────────────────────────────────────────────────

def detect_signal(message: str, recent_keywords: list[str]) -> CuriositySignal:
    """
    Classify the curiosity signal in this message.
    `recent_keywords` are the keywords from the last 3 turns — used to detect
    a child returning to a topic without re-stating it explicitly.
    """
    text = message.strip()

    # Return to prior topic (child still thinking about it)
    if recent_keywords and _CONTINUATION.match(text):
        return {"type": "return", "heat_delta": _HEAT_RETURN, "keywords": recent_keywords}

    # Check for keywords from recent turns appearing again (implicit return)
    lower = text.lower()
    returning = [kw for kw in recent_keywords if kw in lower]
    if len(returning) >= 2:
        return {"type": "return", "heat_delta": _HEAT_RETURN * 0.7, "keywords": returning}

    if _WHY.search(text):
        words = _extract_keywords(text)
        return {"type": "why", "heat_delta": _HEAT_WHY, "keywords": words}

    if _PUSHBACK.search(text):
        words = _extract_keywords(text)
        return {"type": "pushback", "heat_delta": _HEAT_PUSHBACK, "keywords": words}

    if _SPECULATE.search(text):
        words = _extract_keywords(text)
        return {"type": "speculate", "heat_delta": _HEAT_SPECULATE, "keywords": words}

    if _CONNECT.search(text):
        words = _extract_keywords(text)
        return {"type": "connect", "heat_delta": _HEAT_CONNECT, "keywords": words}

    return {"type": "none", "heat_delta": 0.0, "keywords": []}


def _extract_keywords(text: str) -> list[str]:
    """Pull content words > 4 chars, ignore stopwords."""
    _STOP = {
        "that", "this", "with", "from", "have", "will", "what", "when",
        "where", "which", "there", "their", "about", "would", "could",
        "should", "does", "because", "think", "know", "understand",
        "right", "like", "just", "also", "okay", "then", "than",
    }
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    return [w for w in words if w not in _STOP][:6]


# ── Thread management ─────────────────────────────────────────────────────────

def update_threads(
    threads: list[Thread],
    signal: CuriositySignal,
    message: str,
) -> list[Thread]:
    """
    Update the live thread list given a new signal.
    - Decay all threads' heat
    - If signal is meaningful, boost the best-matching thread or start a new one
    - Prune dead threads (heat < 0.05)
    Returns updated thread list (max 5 threads).
    """
    # Decay all
    for t in threads:
        t["heat"] = round(t["heat"] * _HEAT_DECAY, 3)

    if signal["type"] == "none" or not signal["keywords"]:
        return [t for t in threads if t["heat"] >= 0.05]

    # Find best matching existing thread
    best_idx = _best_match(threads, signal["keywords"])

    if best_idx is not None:
        t = threads[best_idx]
        t["heat"] = min(1.0, t["heat"] + signal["heat_delta"])
        t["times_returned"] += 1
        t["last_seen"] = _now()
        t["keywords"] = list(dict.fromkeys(t["keywords"] + signal["keywords"]))[:8]
    else:
        # New thread
        new_thread: Thread = {
            "thread_id": f"t{len(threads)+1}_{date.today().isoformat()}",
            "seed_question": message[:120],
            "keywords": signal["keywords"],
            "heat": signal["heat_delta"],
            "times_returned": 1,
            "first_seen": _now(),
            "last_seen": _now(),
        }
        threads.append(new_thread)

    # Prune and cap
    alive = [t for t in threads if t["heat"] >= 0.05]
    alive.sort(key=lambda t: t["heat"], reverse=True)
    return alive[:5]


def dominant_thread(threads: list[Thread]) -> Thread | None:
    if not threads:
        return None
    best = max(threads, key=lambda t: t["heat"])
    return best if best["heat"] >= 0.15 else None


def _best_match(threads: list[Thread], keywords: list[str]) -> int | None:
    if not threads or not keywords:
        return None
    kw_set = set(keywords)
    best_score, best_idx = 0, None
    for i, t in enumerate(threads):
        overlap = len(kw_set & set(t["keywords"]))
        if overlap > best_score:
            best_score, best_idx = overlap, i
    return best_idx if best_score >= 1 else None


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── DB persistence ────────────────────────────────────────────────────────────

async def load(conn, learner_id: str, session_id: str) -> list[Thread]:
    row = await conn.fetchrow(
        "SELECT threads_json FROM learner_state.curiosity_sessions "
        "WHERE learner_id = $1 AND session_id = $2",
        learner_id, session_id,
    )
    if not row:
        return []
    try:
        return json.loads(row["threads_json"])
    except Exception:
        return []


async def save(conn, learner_id: str, session_id: str, threads: list[Thread]) -> None:
    await conn.execute(
        """
        INSERT INTO learner_state.curiosity_sessions
            (learner_id, session_id, threads_json, updated_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (learner_id, session_id) DO UPDATE
            SET threads_json = EXCLUDED.threads_json,
                updated_at   = now()
        """,
        learner_id, session_id, json.dumps(threads),
    )


async def get_recent_keywords(conn, learner_id: str, session_id: str, n: int = 3) -> list[str]:
    """Keywords from the last N turns in this session — used for return detection."""
    threads = await load(conn, learner_id, session_id)
    if not threads:
        return []
    top = sorted(threads, key=lambda t: t["last_seen"], reverse=True)[:n]
    keywords: list[str] = []
    for t in top:
        keywords.extend(t["keywords"])
    return list(dict.fromkeys(keywords))[:10]


# ── Context injection ─────────────────────────────────────────────────────────

def build_curiosity_context(threads: list[Thread]) -> str:
    """
    Returns a short string to inject into Parth's system prompt.
    Only fires if there's a dominant thread with real heat.
    """
    dominant = dominant_thread(threads)
    if not dominant:
        return ""

    heat_label = (
        "high" if dominant["heat"] > 0.55
        else "medium" if dominant["heat"] > 0.30
        else "low"
    )
    returned = dominant["times_returned"]
    seed = dominant["seed_question"][:100]

    lines = [f"Active curiosity ({heat_label} heat): \"{seed}\""]
    if returned > 1:
        lines.append(f"The child has returned to this thread {returned} times — it's genuinely live.")
    if len(threads) > 1:
        other = [t["seed_question"][:60] for t in threads[1:3]]
        lines.append(f"Secondary threads: {'; '.join(other)}")
    lines.append("Follow the dominant thread if there is a natural opportunity.")

    return "\n".join(lines)
