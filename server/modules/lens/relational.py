"""
Relational Lens — longitudinal portrait of a learner's curiosity, persistence,
and relationship with Parth.

Distinct from the 15 per-message micro-agents:
  • Micro-agents fire on every message → write raw signals to DB
  • This lens reads across accumulated DB state → synthesises a portrait

Reads from:
  learner_state.open_loops         curiosity threads (question, status, created_at, closed_at)
  learner_state.episodes           memorable moments (breakthrough/belief/question/struggle/
                                   connection/awe) with referenced_count
  learner_state.challenge_state    consecutive_struggles, frustration_threshold, difficulty_level
  learner_state.inquiry_state      repair_count, last_repair_at
  learner_state.kt_events          correct, elapsed_ms, lag_ms, created_at (last N days)
  learner_state.profiles           sessions, total_questions, name, grade

Produces:
  RelationalPortrait dataclass  →  stored as JSONB in learner_state.lens_portraits
  narrative: str                →  LLM-generated prose (150-200 words) for
                                   guardian reports, teacher summaries, BMAD review

BMAD flags surface signals that suggest the micro-agent configuration needs
revisiting — e.g. inquiry_alchemist should follow up on open loops more explicitly.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("lens.relational")

# ── Constants ─────────────────────────────────────────────────────────────────
_WINDOW = 30                   # days of kt_events to analyse
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
    "for", "with", "about", "from", "into", "that", "this", "it", "i",
    "what", "why", "how", "when", "where", "who", "which", "if", "but",
    "and", "or", "not", "so", "we", "you", "they", "he", "she", "my",
    "your", "his", "her", "our", "their", "its", "there", "here", "just",
    "then", "than", "also", "up", "out", "get", "let", "like", "very",
})

# Thresholds for learner_identity classification
_CURIOSITY_HIGH  = 0.15   # open_loops / total_questions > this = explorer signal
_CURIOSITY_LOW   = 0.03
_RESOLUTION_HIGH = 0.60   # closed / total loops
_ESTABLISHED_REF = 4.0    # avg referenced_count for "established" relationship
_NEW_SESSIONS    = 3      # fewer than this → "new"
_DISTANT_REF     = 1.5    # many sessions but avg ref < this → "distant"


# ── Portrait dataclass ────────────────────────────────────────────────────────

@dataclass
class OpenLoopSummary:
    question: str
    status: str          # 'open' | 'closed' | 'expired'
    created_at: str
    closed_at: Optional[str]


@dataclass
class EpisodeSummary:
    episode_type: str
    summary: str
    verbatim: str
    referenced_count: int
    created_at: str


@dataclass
class RelationalPortrait:
    learner_id: str
    computed_at: str
    period_days: int

    # Curiosity & follow-through
    curiosity_index: float               # open_loops / total_questions
    open_loop_resolution_rate: float     # closed_loops / total_loops
    open_loops_count: int
    closed_loops_count: int
    total_loops: int

    # Persistence (from kt_events)
    persistence_score: float             # correct-after-wrong ratio per concept

    # Learner identity
    learner_identity: str                # "explorer" | "achiever" | "steady" | "struggling"

    # Breakthrough highlights (top 3)
    breakthrough_moments: list[EpisodeSummary]

    # Curiosity themes
    question_themes: list[tuple[str, int]]   # [(word, count), ...] top 10

    # Struggle-to-breakthrough pattern
    struggle_to_breakthrough_pattern: Optional[float]   # avg struggles before breakthrough

    # Relationship with Parth
    relationship_with_parth: str         # "new" | "warming" | "established" | "distant"

    # Episode counts by type
    episode_counts: dict[str, int]

    # Challenge state snapshot
    consecutive_struggles: int
    frustration_threshold: float
    difficulty_level: float

    # Inquiry state snapshot
    repair_count: int

    # BMAD feedback flags
    bmad_flags: list[str]

    # LLM-generated prose
    narrative: str = ""


# ── DB queries ────────────────────────────────────────────────────────────────

async def _fetch_open_loops(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT question, status, created_at, closed_at
           FROM learner_state.open_loops
           WHERE learner_id = $1
           ORDER BY created_at ASC""",
        learner_id,
    )]


async def _fetch_episodes(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT episode_type, verbatim, summary, referenced_count, created_at
           FROM learner_state.episodes
           WHERE learner_id = $1
           ORDER BY created_at ASC""",
        learner_id,
    )]


async def _fetch_challenge_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT consecutive_struggles, frustration_threshold, difficulty_level
           FROM learner_state.challenge_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {
        "consecutive_struggles": 0,
        "frustration_threshold": 3.0,
        "difficulty_level": 0.5,
    }


async def _fetch_inquiry_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT repair_count, last_repair_at
           FROM learner_state.inquiry_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {"repair_count": 0, "last_repair_at": None}


async def _fetch_kt_events(conn, learner_id: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, correct, elapsed_ms, lag_ms, created_at
           FROM learner_state.kt_events
           WHERE learner_id = $1 AND created_at >= $2
           ORDER BY created_at ASC""",
        learner_id, since,
    )]


async def _fetch_profile(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT name, grade, sessions, total_questions
           FROM learner_state.profiles
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _curiosity_index(open_loops: list[dict], total_questions: int) -> float:
    """open_loops count / total_questions — how often does this child ask questions?"""
    if total_questions <= 0:
        return 0.0
    return round(len(open_loops) / total_questions, 4)


def _resolution_rate(open_loops: list[dict]) -> tuple[float, int, int]:
    """(closed / total, closed_count, total_count)"""
    total = len(open_loops)
    if total == 0:
        return 0.0, 0, 0
    closed = sum(1 for l in open_loops if l["status"] == "closed")
    return round(closed / total, 4), closed, total


def _persistence_score(kt_events: list[dict]) -> float:
    """
    Ratio of correct answers that came after a wrong answer on the same concept.
    Per concept: look at the event sequence. Count (wrong → correct) transitions.
    persistence = sum(recovered_correct) / sum(all_correct)
    """
    if not kt_events:
        return 0.0

    # Group events by concept, preserving order
    by_concept: dict[str, list[bool]] = {}
    for e in kt_events:
        by_concept.setdefault(e["concept_id"], []).append(bool(e["correct"]))

    total_correct = 0
    recovered_correct = 0
    for outcomes in by_concept.values():
        for i, correct in enumerate(outcomes):
            if correct:
                total_correct += 1
                if i > 0 and not outcomes[i - 1]:
                    recovered_correct += 1

    if total_correct == 0:
        return 0.0
    return round(recovered_correct / total_correct, 4)


def _episode_counts(episodes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {
        "breakthrough": 0, "belief": 0, "question": 0,
        "struggle": 0, "connection": 0, "awe": 0,
    }
    for e in episodes:
        counts[e["episode_type"]] = counts.get(e["episode_type"], 0) + 1
    return counts


def _learner_identity(
    curiosity_idx: float,
    resolution_rate: float,
    ep_counts: dict[str, int],
    persistence: float,
) -> str:
    """
    "explorer"   — high curiosity_index, many awe/question episodes
    "achiever"   — many breakthrough episodes, high persistence (tried and got it)
    "steady"     — consistent, low volatility (low struggles and low breakthroughs)
    "struggling" — high struggle episodes, low breakthrough
    """
    total_ep = sum(ep_counts.values()) or 1
    breakthrough_frac = ep_counts.get("breakthrough", 0) / total_ep
    struggle_frac     = ep_counts.get("struggle", 0) / total_ep
    awe_q_frac        = (ep_counts.get("awe", 0) + ep_counts.get("question", 0)) / total_ep

    # Explorer: asks lots of questions, high wonder moments
    if curiosity_idx >= _CURIOSITY_HIGH and awe_q_frac >= 0.25:
        return "explorer"

    # Achiever: lots of breakthroughs, tries again and gets it
    if breakthrough_frac >= 0.25 and persistence >= 0.35:
        return "achiever"

    # Struggling: high struggle, low breakthrough
    if struggle_frac >= 0.30 and breakthrough_frac < 0.15:
        return "struggling"

    # Default: steady
    return "steady"


def _breakthrough_moments(episodes: list[dict], top_n: int = 3) -> list[EpisodeSummary]:
    """Top N breakthrough episodes by referenced_count, then recency."""
    breakthroughs = [e for e in episodes if e["episode_type"] == "breakthrough"]
    breakthroughs.sort(key=lambda e: (e["referenced_count"], e["created_at"]), reverse=True)
    return [
        EpisodeSummary(
            episode_type=e["episode_type"],
            summary=e["summary"],
            verbatim=e["verbatim"],
            referenced_count=e["referenced_count"],
            created_at=(e["created_at"].isoformat()
                        if hasattr(e["created_at"], "isoformat") else str(e["created_at"])),
        )
        for e in breakthroughs[:top_n]
    ]


def _question_themes(open_loops: list[dict], top_n: int = 10) -> list[tuple[str, int]]:
    """
    Simple word-frequency over open_loop questions.
    No NLP — just split, lowercase, strip punctuation, filter stopwords.
    Returns [(word, count)] sorted descending.
    """
    counter: Counter = Counter()
    for loop in open_loops:
        text = loop.get("question", "")
        words = re.findall(r"[a-zA-Z]+", text.lower())
        for w in words:
            if len(w) > 2 and w not in _STOPWORDS:
                counter[w] += 1
    return counter.most_common(top_n)


def _struggle_to_breakthrough_pattern(episodes: list[dict]) -> Optional[float]:
    """
    Average number of struggle episodes immediately preceding each breakthrough episode,
    computed from the chronological episode sequence.
    Returns None if there are no breakthrough episodes.
    """
    if not episodes:
        return None

    # Episodes are already ordered by created_at ASC from the query
    breakthrough_indices = [i for i, e in enumerate(episodes) if e["episode_type"] == "breakthrough"]
    if not breakthrough_indices:
        return None

    counts = []
    for bt_idx in breakthrough_indices:
        # Count consecutive struggles immediately before this breakthrough
        n = 0
        j = bt_idx - 1
        while j >= 0 and episodes[j]["episode_type"] == "struggle":
            n += 1
            j -= 1
        counts.append(n)

    return round(statistics.mean(counts), 2)


def _relationship_with_parth(
    episodes: list[dict],
    sessions: int,
) -> str:
    """
    "new"         — fewer than _NEW_SESSIONS sessions
    "established" — high avg referenced_count across episodes
    "warming"     — referenced_count increasing over time (first-half avg < second-half avg)
    "distant"     — many sessions but low referenced_count
    """
    if sessions < _NEW_SESSIONS:
        return "new"

    if not episodes:
        return "distant"

    ref_counts = [e["referenced_count"] for e in episodes]
    avg_ref = statistics.mean(ref_counts)

    if avg_ref >= _ESTABLISHED_REF:
        return "established"

    # Check warming: compare first-half vs second-half average referenced_count
    mid = len(ref_counts) // 2
    if mid > 0:
        first_half_avg  = statistics.mean(ref_counts[:mid])
        second_half_avg = statistics.mean(ref_counts[mid:])
        if second_half_avg > first_half_avg + 0.5:
            return "warming"

    if sessions >= 5 and avg_ref < _DISTANT_REF:
        return "distant"

    return "warming"


def _bmad_flags(
    curiosity_idx: float,
    resolution_rate: float,
    ep_counts: dict[str, int],
    persistence: float,
    consecutive_struggles: int,
    frustration_threshold: float,
    open_loops: list[dict],
    sessions: int,
    relationship: str,
) -> list[str]:
    flags = []

    # High curiosity but low resolution — inquiry_alchemist should follow up
    if curiosity_idx >= _CURIOSITY_HIGH and resolution_rate < 0.3:
        flags.append(
            "curiosity_index high but open_loop_resolution_rate low — "
            "inquiry_alchemist should follow up on open loops more explicitly."
        )

    # Struggling identity with no repair signal
    struggle_count = ep_counts.get("struggle", 0)
    breakthrough_count = ep_counts.get("breakthrough", 0)
    if struggle_count >= 4 and breakthrough_count == 0:
        flags.append(
            f"{struggle_count} struggle episodes recorded with zero breakthroughs — "
            "challenge_calibrator may be pitching difficulty too high; "
            "consider reducing difficulty_level."
        )

    # Consecutive struggles near threshold
    if consecutive_struggles >= int(frustration_threshold):
        flags.append(
            f"consecutive_struggles ({consecutive_struggles}) has reached frustration_threshold "
            f"({frustration_threshold:.1f}) — check whether challenge_calibrator backed off "
            "difficulty in time."
        )

    # Many open loops, none closed — stale curiosity threads
    open_count = sum(1 for l in open_loops if l["status"] == "open")
    if open_count >= 5:
        flags.append(
            f"{open_count} open loops still unresolved — "
            "open_loop_generator may be planting wonders faster than they are revisited."
        )

    # Low curiosity across many sessions — engagement risk
    if sessions >= 6 and curiosity_idx < _CURIOSITY_LOW:
        flags.append(
            "Very low curiosity_index despite multiple sessions — "
            "learner may not be asking questions organically; "
            "inquiry_alchemist should model more open-ended wondering."
        )

    # Distant relationship with high session count
    if relationship == "distant" and sessions >= 8:
        flags.append(
            "Relationship with Parth rated 'distant' after 8+ sessions — "
            "episode memory is under-utilised; check whether episodic_mentor "
            "is referencing past episodes in responses."
        )

    # Low persistence: tries but doesn't recover
    if persistence < 0.15 and struggle_count >= 3:
        flags.append(
            f"Low persistence_score ({persistence:.2f}) with {struggle_count} struggle episodes — "
            "learner is not recovering after errors on the same concept; "
            "consider scaffolded hints before re-attempt."
        )

    return flags


# ── LLM narrative ─────────────────────────────────────────────────────────────

async def _generate_narrative(portrait: RelationalPortrait, profile: dict) -> str:
    """
    Call the local LLM to produce 150-200 words of warm, teacher-voice prose
    for a guardian report. Falls back to a template string on failure.
    """
    name  = profile.get("name") or portrait.learner_id
    grade = profile.get("grade", "?")

    # Prepare readable snippets
    breakthrough_str = "; ".join(
        f'"{m.summary}"' for m in portrait.breakthrough_moments
    ) or "none recorded yet"

    theme_str = ", ".join(w for w, _ in portrait.question_themes[:5]) or "no clear themes yet"

    struggle_gap = (
        f"{portrait.struggle_to_breakthrough_pattern} struggle episodes on average"
        if portrait.struggle_to_breakthrough_pattern is not None
        else "not yet established"
    )

    ep = portrait.episode_counts
    episode_str = (
        f"{ep.get('breakthrough', 0)} breakthroughs, "
        f"{ep.get('struggle', 0)} struggles, "
        f"{ep.get('awe', 0)} moments of awe, "
        f"{ep.get('question', 0)} deep questions"
    )

    system_msg = (
        "You are a learning mentor writing a warm, personal portrait of a child "
        "for their teacher or guardian. Use plain, caring language. "
        "Be specific — cite actual words the child said, moments they had, "
        "things they wondered about. 150–200 words. "
        "Do not use bullet points. Write in continuous prose. "
        "Focus on who this child IS as a learner, not just what they scored."
    )

    user_msg = f"""Write a relational learning portrait for {name}, Grade {grade}.

Data:
- Learner identity: {portrait.learner_identity}
- Curiosity index: {portrait.curiosity_index:.2f} (open questions / total answered)
- Open-loop resolution rate: {portrait.open_loop_resolution_rate:.0%} of questions followed through
- Persistence score: {portrait.persistence_score:.2f} (recovered correct answers after wrong)
- Relationship with Parth: {portrait.relationship_with_parth}
- Episode summary: {episode_str}
- Breakthrough moments: {breakthrough_str}
- Question themes (what they wonder about): {theme_str}
- Struggle-to-breakthrough pattern: {struggle_gap}
- Open loops still unresolved: {portrait.open_loops_count - portrait.closed_loops_count}

Write the portrait now."""

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.FAST_MODEL,
                    "messages": [
                        {"role": "user", "content": system_msg},
                        {"role": "assistant", "content": "Understood. Here is the portrait:"},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.4},
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
    except Exception as exc:
        log.warning("narrative_llm_failed", error=str(exc))
        return (
            f"{name} (Grade {grade}) is a {portrait.learner_identity} learner. "
            f"Curiosity index: {portrait.curiosity_index:.2f}; "
            f"follows through on {portrait.open_loop_resolution_rate:.0%} of open questions. "
            f"Persistence score: {portrait.persistence_score:.2f}. "
            f"Relationship with Parth: {portrait.relationship_with_parth}. "
            f"Breakthrough moments: {breakthrough_str}. "
            f"Wonders about: {theme_str}."
        )


# ── Persistence ───────────────────────────────────────────────────────────────

async def _save_portrait(conn, portrait: RelationalPortrait) -> None:
    data = asdict(portrait)
    narrative = data.pop("narrative", "")
    # question_themes is a list of tuples — serialise as list of lists for JSONB
    data["question_themes"] = [list(t) for t in data.get("question_themes", [])]
    await conn.execute(
        """INSERT INTO learner_state.lens_portraits
           (learner_id, lens, portrait, narrative, computed_at, period_start, period_end)
           VALUES ($1, 'relational', $2, $3, now(),
                   now() - ($4 || ' days')::interval, now())""",
        portrait.learner_id,
        json.dumps(data),
        narrative,
        str(portrait.period_days),
    )


async def _fetch_latest(conn, learner_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """SELECT portrait, narrative, computed_at, period_start, period_end
           FROM learner_state.lens_portraits
           WHERE learner_id = $1 AND lens = 'relational'
           ORDER BY computed_at DESC LIMIT 1""",
        learner_id,
    )
    if not row:
        return None
    data = dict(row["portrait"])
    data["narrative"]    = row["narrative"]
    data["computed_at"]  = row["computed_at"].isoformat()
    data["period_start"] = row["period_start"].isoformat() if row["period_start"] else None
    data["period_end"]   = row["period_end"].isoformat()   if row["period_end"]   else None
    return data


# ── Public API ────────────────────────────────────────────────────────────────

async def compute(
    conn, learner_id: str, period_days: int = _WINDOW
) -> tuple["RelationalPortrait", dict]:
    """
    Run the full Relational Lens computation for one learner.

    Three phases to avoid holding the DB connection across the slow Ollama call:
      1. Read    — fetch all DB state (conn held briefly, sequential awaits)
      2. Compute — pure Python, no DB
      3. Narrate — Ollama HTTP call (caller releases conn before this)
      4. Persist — re-acquire conn to save result

    Returns (RelationalPortrait, profile_dict).
    The profile_dict is needed by _generate_narrative after the conn is released.
    """
    log.info("relational_lens_start", learner_id=learner_id, period_days=period_days)

    # Phase 1 — sequential DB reads (asyncpg: one operation at a time per conn)
    open_loops      = await _fetch_open_loops(conn, learner_id)
    episodes        = await _fetch_episodes(conn, learner_id)
    challenge       = await _fetch_challenge_state(conn, learner_id)
    inquiry         = await _fetch_inquiry_state(conn, learner_id)
    kt_events       = await _fetch_kt_events(conn, learner_id, period_days)
    profile         = await _fetch_profile(conn, learner_id)

    # Phase 2 — pure computation (no DB, no network)
    total_questions = int(profile.get("total_questions") or 0)
    sessions        = int(profile.get("sessions") or 0)

    curiosity_idx             = _curiosity_index(open_loops, total_questions)
    res_rate, closed, total   = _resolution_rate(open_loops)
    persistence               = _persistence_score(kt_events)
    ep_counts                 = _episode_counts(episodes)
    identity                  = _learner_identity(curiosity_idx, res_rate, ep_counts, persistence)
    breakthroughs             = _breakthrough_moments(episodes)
    themes                    = _question_themes(open_loops)
    s2b_pattern               = _struggle_to_breakthrough_pattern(episodes)
    relationship              = _relationship_with_parth(episodes, sessions)
    flags                     = _bmad_flags(
        curiosity_idx, res_rate, ep_counts, persistence,
        int(challenge["consecutive_struggles"]),
        float(challenge["frustration_threshold"]),
        open_loops, sessions, relationship,
    )

    portrait = RelationalPortrait(
        learner_id=learner_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,
        curiosity_index=curiosity_idx,
        open_loop_resolution_rate=res_rate,
        open_loops_count=len(open_loops),
        closed_loops_count=closed,
        total_loops=total,
        persistence_score=persistence,
        learner_identity=identity,
        breakthrough_moments=breakthroughs,
        question_themes=themes,
        struggle_to_breakthrough_pattern=s2b_pattern,
        relationship_with_parth=relationship,
        episode_counts=ep_counts,
        consecutive_struggles=int(challenge["consecutive_struggles"]),
        frustration_threshold=float(challenge["frustration_threshold"]),
        difficulty_level=float(challenge["difficulty_level"]),
        repair_count=int(inquiry.get("repair_count") or 0),
        bmad_flags=flags,
    )

    log.info(
        "relational_lens_computed",
        learner_id=learner_id,
        identity=identity,
        relationship=relationship,
        flags=len(flags),
    )
    return portrait, profile


async def compute_and_save(
    pool, learner_id: str, period_days: int = _WINDOW
) -> RelationalPortrait:
    """
    Full pipeline with correct connection lifecycle:
      Phase 1+2: read + compute on one conn → release conn
      Phase 3:   LLM narrative (Ollama, slow, no conn needed)
      Phase 4:   re-acquire conn → save portrait

    The API endpoint calls this instead of compute() directly.
    """
    # Phases 1 + 2: DB reads and pure computation
    async with pool.acquire() as conn:
        portrait, profile = await compute(conn, learner_id, period_days)
    # conn released here before Ollama call

    # Phase 3: LLM narrative — no DB connection held during this
    portrait.narrative = await _generate_narrative(portrait, profile)

    # Phase 4: persist
    async with pool.acquire() as conn2:
        try:
            await _save_portrait(conn2, portrait)
        except Exception as exc:
            log.warning("portrait_save_failed", error=str(exc))

    log.info(
        "relational_lens_done",
        learner_id=learner_id,
        narrative_len=len(portrait.narrative),
    )
    return portrait


async def latest(conn, learner_id: str) -> Optional[dict]:
    """Return the most recently computed portrait without recomputing."""
    return await _fetch_latest(conn, learner_id)
