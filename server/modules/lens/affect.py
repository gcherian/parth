"""
Affect Lens — longitudinal portrait of a learner's emotional trajectory.

Distinct from the 15 per-message micro-agents:
  • Micro-agents fire on every message → write raw signals to DB
  • This lens reads across accumulated DB state → synthesises a portrait

Reads from:
  learner_state.affect_state        current emotion probability vector (frustration,
                                    confusion, boredom, curiosity, delight, uncertainty)
  learner_state.emotion_history     time-series of recorded emotions + engagement scores
  learner_state.profiles            name, grade, sessions, last_emotion, engagement_score
  learner_state.challenge_state     consecutive_struggles, frustration_threshold,
                                    difficulty_level
  learner_state.delight_state       humor_tolerance, delight_triggers, nogo_zones

Produces:
  AffectPortrait dataclass  →  stored as JSONB in learner_state.lens_portraits
  narrative: str            →  LLM-generated prose (150-200 words) for
                               guardian reports, teacher summaries, BMAD review

BMAD flags surface signals that suggest the micro-agent configuration needs
revisiting — e.g. frustration threshold too low, insufficient delight scaffolding.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("lens.affect")

# ── Constants ─────────────────────────────────────────────────────────────────
_WINDOW              = 30                            # days of emotion_history to analyse
_DISTRESS_EMOTIONS   = {"frustration", "frustrated", "distress", "anxious", "anxiety"}
_POSITIVE_EMOTIONS   = {"curious", "curiosity", "excited", "excitement", "delight", "delighted"}
_NEUTRAL_EMOTIONS    = {"neutral", "calm", "focused"}
_RECOVERY_TARGET     = _POSITIVE_EMOTIONS | _NEUTRAL_EMOTIONS


# ── Portrait dataclass ────────────────────────────────────────────────────────

@dataclass
class WeeklyEmotionSlice:
    week_start: str                     # ISO date of Monday
    dominant_emotion: str
    avg_engagement: float


@dataclass
class DelightTrigger:
    emotion: str
    avg_engagement: float
    occurrence_count: int


@dataclass
class AffectPortrait:
    learner_id: str
    computed_at: str
    period_days: int

    # Current state snapshot
    current_frustration: float
    current_confusion: float
    current_boredom: float
    current_curiosity: float
    current_delight: float
    current_uncertainty: float

    # History-derived signals
    dominant_emotion: str               # most frequent in window
    emotion_arc: list[WeeklyEmotionSlice]   # week-by-week trend
    distress_frequency: float           # fraction of events that are distress-family
    engagement_trend: str               # "rising" | "falling" | "stable"

    # Positive engagement
    delight_triggers: list[DelightTrigger]  # emotions tagged curious/excited, with avg eng

    # Recovery
    recovery_speed: Optional[float]     # avg interactions from frustrated → neutral/positive

    # Challenge context
    consecutive_struggles: int
    frustration_threshold: float
    difficulty_level: float

    # Delight state
    humor_tolerance: float
    known_delight_triggers: list[str]   # from delight_state.delight_triggers (JSON list)
    nogo_zones: list[str]               # from delight_state.nogo_zones (JSON list)

    # BMAD feedback flags
    bmad_flags: list[str]

    # LLM-generated prose
    narrative: str = ""


# ── DB queries ────────────────────────────────────────────────────────────────

async def _fetch_affect_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT frustration, confusion, boredom, curiosity, delight, uncertainty
           FROM learner_state.affect_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_emotion_history(conn, learner_id: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [dict(r) for r in await conn.fetch(
        """SELECT emotion, engagement, recorded_at
           FROM learner_state.emotion_history
           WHERE learner_id = $1 AND recorded_at >= $2
           ORDER BY recorded_at ASC""",
        learner_id, since,
    )]


async def _fetch_profile(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT name, grade, sessions, engagement_score, last_emotion
           FROM learner_state.profiles
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_challenge_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT consecutive_struggles, frustration_threshold, difficulty_level
           FROM learner_state.challenge_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_delight_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT humor_tolerance, delight_triggers, nogo_zones
           FROM learner_state.delight_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _dominant_emotion(history: list[dict]) -> str:
    """Most frequently recorded emotion over the window."""
    if not history:
        return "unknown"
    counts = Counter(e["emotion"].lower() for e in history)
    return counts.most_common(1)[0][0]


def _emotion_arc(history: list[dict]) -> list[WeeklyEmotionSlice]:
    """
    Group emotion_history into ISO weeks; for each week compute dominant emotion
    and average engagement score.
    """
    if not history:
        return []

    # Group by calendar week (Monday-anchored)
    weeks: dict[str, list[dict]] = {}
    for e in history:
        ts = e["recorded_at"]
        if hasattr(ts, "isocalendar"):
            iso = ts.isocalendar()               # (year, week, weekday)
            # Reconstruct the Monday of that ISO week
            monday = ts - timedelta(days=ts.weekday())
            key = monday.date().isoformat()
        else:
            key = str(ts)[:10]                   # fallback: date string
        weeks.setdefault(key, []).append(e)

    arc = []
    for week_start in sorted(weeks.keys()):
        events = weeks[week_start]
        dominant = Counter(ev["emotion"].lower() for ev in events).most_common(1)[0][0]
        avg_eng  = round(statistics.mean(float(ev["engagement"]) for ev in events), 3)
        arc.append(WeeklyEmotionSlice(
            week_start=week_start,
            dominant_emotion=dominant,
            avg_engagement=avg_eng,
        ))
    return arc


def _distress_frequency(history: list[dict]) -> float:
    """Fraction of emotion events that belong to the distress family."""
    if not history:
        return 0.0
    distress_count = sum(
        1 for e in history if e["emotion"].lower() in _DISTRESS_EMOTIONS
    )
    return round(distress_count / len(history), 3)


def _engagement_trend(history: list[dict]) -> str:
    """
    Compare average engagement in the first vs second half of the window.
    Rising / falling / stable based on ±0.05 threshold.
    """
    if len(history) < 6:
        return "stable"

    mid          = len(history) // 2
    first_half   = history[:mid]
    second_half  = history[mid:]

    avg_first  = statistics.mean(float(e["engagement"]) for e in first_half)
    avg_second = statistics.mean(float(e["engagement"]) for e in second_half)
    delta = avg_second - avg_first

    if delta > 0.05:
        return "rising"
    elif delta < -0.05:
        return "falling"
    return "stable"


def _delight_triggers(history: list[dict]) -> list[DelightTrigger]:
    """
    Emotions tagged as curious/excited variant: group, compute avg engagement and count.
    Sorted by avg engagement descending.
    """
    buckets: dict[str, list[float]] = {}
    for e in history:
        em = e["emotion"].lower()
        if em in _POSITIVE_EMOTIONS:
            buckets.setdefault(em, []).append(float(e["engagement"]))

    triggers = [
        DelightTrigger(
            emotion=em,
            avg_engagement=round(statistics.mean(vals), 3),
            occurrence_count=len(vals),
        )
        for em, vals in buckets.items()
    ]
    triggers.sort(key=lambda t: t.avg_engagement, reverse=True)
    return triggers


def _recovery_speed(history: list[dict]) -> Optional[float]:
    """
    Proxy: find sequences where a frustrated/distress event is followed by a
    neutral/positive event. Count the number of intervening events (0 = immediate
    recovery). Return the average gap count, or None if no frustration events found.
    """
    if not history:
        return None

    gaps: list[int] = []
    in_distress = False
    gap_count   = 0

    for e in history:
        em = e["emotion"].lower()
        if em in _DISTRESS_EMOTIONS:
            in_distress = True
            gap_count   = 0
        elif in_distress:
            if em in _RECOVERY_TARGET:
                gaps.append(gap_count)
                in_distress = False
                gap_count   = 0
            else:
                gap_count += 1

    if not gaps:
        return None
    return round(statistics.mean(gaps), 2)


def _parse_json_list(raw, default: list) -> list:
    """Safe parser for JSON-encoded list columns (delight_triggers, nogo_zones)."""
    if raw is None:
        return default
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else default
    except (json.JSONDecodeError, TypeError):
        return default


def _bmad_flags(
    history: list[dict],
    affect: dict,
    challenge: dict,
    distress_freq: float,
    engagement_trend_label: str,
    arc: list[WeeklyEmotionSlice],
    recovery: Optional[float],
) -> list[str]:
    flags = []

    # Persistently high frustration in affect_state
    if float(affect.get("frustration", 0)) > 0.5:
        flags.append(
            "Current frustration probability > 0.50 — emotion_compass thresholds may be "
            "too permissive; consider lowering frustration_threshold in challenge_state."
        )

    # High distress frequency in history
    if distress_freq > 0.40:
        flags.append(
            f"Distress-family emotions account for {distress_freq:.0%} of recorded events — "
            "challenge_calibrator difficulty ceiling may be too high; recommend difficulty audit."
        )

    # Consecutive struggles still climbing
    consec = int(challenge.get("consecutive_struggles", 0))
    thresh = float(challenge.get("frustration_threshold", 3.0))
    if consec >= thresh:
        flags.append(
            f"consecutive_struggles ({consec}) has reached frustration_threshold ({thresh:.1f}) — "
            "difficulty_adjuster may not be triggering correctly; check challenge_calibrator logic."
        )

    # Falling engagement trend
    if engagement_trend_label == "falling":
        flags.append(
            "Engagement trend is falling over the analysis window — "
            "consider increasing delight scaffolding or reducing repetition in curriculum_cartographer."
        )

    # Slow recovery speed
    if recovery is not None and recovery > 5:
        flags.append(
            f"Average recovery from distress takes {recovery:.1f} interactions — "
            "inquiry_alchemist SEL repair cadence may need to fire sooner post-frustration."
        )

    # Very few emotion events = insufficient signal
    if len(history) < 5:
        flags.append(
            "Fewer than 5 emotion events in the analysis window — "
            "insufficient signal for a reliable affect portrait; check session frequency."
        )

    # High boredom
    if float(affect.get("boredom", 0)) > 0.45:
        flags.append(
            "Current boredom probability > 0.45 — content variety or pacing may need "
            "adjustment; consider diversity boost in curriculum_cartographer."
        )

    return flags


# ── LLM narrative ─────────────────────────────────────────────────────────────

async def _generate_narrative(portrait: AffectPortrait, profile: dict) -> str:
    """
    Call the local LLM to turn the structured affect portrait into 150-200 words of
    warm, professional prose for a teacher or guardian. Falls back to a template on failure.
    """
    name  = profile.get("name") or portrait.learner_id
    grade = profile.get("grade", "?")

    arc_summary = (
        ", ".join(
            f"wk {s.week_start[-5:]}: {s.dominant_emotion} (eng {s.avg_engagement:.2f})"
            for s in portrait.emotion_arc[-4:]
        ) or "no weekly data"
    )
    triggers_str = (
        ", ".join(
            f"{t.emotion} (avg eng {t.avg_engagement:.2f})"
            for t in portrait.delight_triggers[:3]
        ) or "none identified"
    )
    recovery_str = (
        f"{portrait.recovery_speed:.1f} interactions" if portrait.recovery_speed is not None
        else "not enough data"
    )

    system_msg = (
        "You are a child learning specialist writing a brief emotional wellbeing portrait "
        "for a teacher or parent. Use warm, empathetic, professional language. "
        "Be specific — cite the child's name and actual data from the analysis. "
        "150–200 words. Do not use bullet points. Write in continuous prose. "
        "Do not diagnose or pathologise — frame everything constructively."
    )
    user_msg = f"""Write an affect learning portrait for {name}, Grade {grade}.

Data:
- Dominant emotion over last {portrait.period_days} days: {portrait.dominant_emotion}
- Distress frequency: {portrait.distress_frequency:.0%} of interactions
- Engagement trend: {portrait.engagement_trend}
- Weekly arc (recent 4 weeks): {arc_summary}
- What lights them up (delight triggers): {triggers_str}
- Recovery speed from distress: {recovery_str}
- Current frustration level: {portrait.current_frustration:.2f}
- Current curiosity level: {portrait.current_curiosity:.2f}
- Consecutive struggles at last check: {portrait.consecutive_struggles}
- Known no-go zones: {', '.join(portrait.nogo_zones) or 'none recorded'}

Write the portrait now."""

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.FAST_MODEL,
                    "messages": [
                        {"role": "user",      "content": system_msg},
                        {"role": "assistant", "content": "Understood. Here is the portrait:"},
                        {"role": "user",      "content": user_msg},
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
            f"{name} (Grade {grade}) shows a dominant emotional pattern of "
            f"{portrait.dominant_emotion} over the last {portrait.period_days} days. "
            f"Distress-family emotions account for {portrait.distress_frequency:.0%} of recorded "
            f"interactions, and overall engagement is {portrait.engagement_trend}. "
            f"What appears to energise {name} most: {triggers_str}. "
            f"Recovery from difficult moments takes approximately {recovery_str}. "
            f"Current curiosity sits at {portrait.current_curiosity:.2f} and frustration at "
            f"{portrait.current_frustration:.2f}."
        )


# ── Persistence ───────────────────────────────────────────────────────────────

async def _save_portrait(conn, portrait: AffectPortrait) -> None:
    data = asdict(portrait)
    narrative = data.pop("narrative", "")
    await conn.execute(
        """INSERT INTO learner_state.lens_portraits
           (learner_id, lens, portrait, narrative, computed_at, period_start, period_end)
           VALUES ($1, 'affect', $2, $3, now(),
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
           WHERE learner_id = $1 AND lens = 'affect'
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

async def compute(conn, learner_id: str, period_days: int = _WINDOW) -> tuple[AffectPortrait, dict]:
    """
    Run the full Affect Lens computation for one learner.

    Returns (portrait, profile) — does NOT generate a narrative and does NOT
    save to the DB. Callers that want the full pipeline should use compute_and_save().

    Phase structure (asyncpg: one operation at a time per conn, never gather):
      Sequential DB reads → pure Python computation → return.
    """
    log.info("affect_lens_start", learner_id=learner_id, period_days=period_days)

    # Phase 1 — sequential DB reads (asyncpg: one op at a time per conn)
    affect    = await _fetch_affect_state(conn, learner_id)
    history   = await _fetch_emotion_history(conn, learner_id, period_days)
    profile   = await _fetch_profile(conn, learner_id)
    challenge = await _fetch_challenge_state(conn, learner_id)
    delight   = await _fetch_delight_state(conn, learner_id)

    # Phase 2 — pure computation (no DB, no network)
    dominant     = _dominant_emotion(history)
    arc          = _emotion_arc(history)
    distress_freq = _distress_frequency(history)
    eng_trend    = _engagement_trend(history)
    triggers     = _delight_triggers(history)
    recovery     = _recovery_speed(history)
    flags        = _bmad_flags(
        history, affect, challenge, distress_freq, eng_trend, arc, recovery
    )

    known_triggers = _parse_json_list(
        delight.get("delight_triggers"), default=[]
    )
    nogo_zones = _parse_json_list(
        delight.get("nogo_zones"),
        default=["identity", "religion", "family", "appearance"],
    )

    portrait = AffectPortrait(
        learner_id=learner_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,

        current_frustration=round(float(affect.get("frustration", 0.1)), 3),
        current_confusion=round(float(affect.get("confusion", 0.15)), 3),
        current_boredom=round(float(affect.get("boredom", 0.1)), 3),
        current_curiosity=round(float(affect.get("curiosity", 0.2)), 3),
        current_delight=round(float(affect.get("delight", 0.1)), 3),
        current_uncertainty=round(float(affect.get("uncertainty", 0.5)), 3),

        dominant_emotion=dominant,
        emotion_arc=arc,
        distress_frequency=distress_freq,
        engagement_trend=eng_trend,
        delight_triggers=triggers,
        recovery_speed=recovery,

        consecutive_struggles=int(challenge.get("consecutive_struggles", 0)),
        frustration_threshold=float(challenge.get("frustration_threshold", 3.0)),
        difficulty_level=round(float(challenge.get("difficulty_level", 0.5)), 3),

        humor_tolerance=round(float(delight.get("humor_tolerance", 0.5)), 3),
        known_delight_triggers=known_triggers,
        nogo_zones=nogo_zones,

        bmad_flags=flags,
    )

    log.info(
        "affect_lens_computed",
        learner_id=learner_id,
        dominant=dominant,
        distress_freq=distress_freq,
        engagement_trend=eng_trend,
        flags=len(flags),
    )
    return portrait, profile


async def compute_and_save(pool, learner_id: str, period_days: int = _WINDOW) -> AffectPortrait:
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

    log.info("affect_lens_done", learner_id=learner_id, narrative_len=len(portrait.narrative))
    return portrait


async def latest(conn, learner_id: str) -> Optional[dict]:
    """Return the most recently computed affect portrait without recomputing."""
    return await _fetch_latest(conn, learner_id)
