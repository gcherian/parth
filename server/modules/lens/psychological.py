"""
Psychological Lens — longitudinal portrait of a learner's emotional and motivational profile.

Distinct from the 15 per-message micro-agents:
  • Micro-agents fire on every message → write raw signals to DB
  • This lens reads across accumulated DB state → synthesises a portrait

Reads from:
  learner_state.psyche                  conscientiousness, growth_mindset, anxiety,
                                        depth_preference, mastery_orientation,
                                        extroversion, thinking_feeling, sample_count
  learner_state.confidence_calibration  concept_id, stated_high, actual_mastery, gap
  learner_state.episodes                breakthrough/belief/question/struggle/
                                        connection/awe events with verbatim & summary
  learner_state.profiles                name, grade, sessions

Produces:
  PsychologicalPortrait dataclass  →  stored as JSONB in learner_state.lens_portraits
  narrative: str                   →  LLM-generated prose (150-200 words) for
                                      guardian reports, teacher summaries, BMAD review

BMAD flags surface motivational or affective signals that suggest the micro-agent
configuration needs revisiting — e.g. belief_coach framing, anxiety scaffolding,
or growth-mindset reinforcement cadence.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("lens.psychological")

# ── Window default ─────────────────────────────────────────────────────────────
_WINDOW = 30  # days of episodes to analyse


# ── Portrait dataclass ─────────────────────────────────────────────────────────

@dataclass
class CalibrationSummary:
    overconfident: int   # stated_high=True, gap > 0.2
    underconfident: int  # stated_high=False, gap < -0.2
    well_calibrated: int # everything else


@dataclass
class PsychologicalPortrait:
    learner_id: str
    computed_at: str
    period_days: int

    # Raw psyche scores (0-1)
    conscientiousness: float
    growth_mindset: float
    anxiety: float
    depth_preference: float
    mastery_orientation: float
    extroversion: float
    thinking_feeling: float
    psyche_sample_count: int

    # Derived labels
    mbti_proxy: str              # e.g. "INTJ"
    mindset_label: str           # "growth" | "mixed" | "fixed"
    anxiety_level: str           # "high" | "moderate" | "low"
    dominant_learning_style: str # "conceptual" | "balanced" | "procedural"
    psychological_readiness: str # "high" | "moderate" | "low"

    # Calibration
    calibration_summary: CalibrationSummary

    # Episodes
    episode_counts: dict          # episode_type → count
    breakthrough_to_struggle_ratio: float

    # BMAD feedback flags
    bmad_flags: list[str]

    # LLM-generated prose
    narrative: str = ""


# ── DB queries ─────────────────────────────────────────────────────────────────

async def _fetch_psyche(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT conscientiousness, growth_mindset, anxiety, depth_preference,
                  mastery_orientation, extroversion, thinking_feeling, sample_count
           FROM learner_state.psyche
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_calibration(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, stated_high, actual_mastery, gap
           FROM learner_state.confidence_calibration
           WHERE learner_id = $1""",
        learner_id,
    )]


async def _fetch_episodes(conn, learner_id: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [dict(r) for r in await conn.fetch(
        """SELECT episode_type, verbatim, summary, concept_ids,
                  referenced_count, created_at
           FROM learner_state.episodes
           WHERE learner_id = $1 AND created_at >= $2
           ORDER BY created_at ASC""",
        learner_id, since,
    )]


async def _fetch_profile(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT name, grade, sessions FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    return dict(row) if row else {}


# ── Analysis helpers ───────────────────────────────────────────────────────────

def _mbti_proxy(psyche: dict) -> str:
    """Derive a 4-letter MBTI proxy from psyche scores (all 0-1)."""
    ei = "E" if psyche.get("extroversion", 0.5) > 0.5 else "I"
    ns = "N" if psyche.get("depth_preference", 0.5) > 0.5 else "S"
    tf = "T" if psyche.get("thinking_feeling", 0.5) > 0.5 else "F"
    jp = "J" if psyche.get("conscientiousness", 0.5) > 0.5 else "P"
    return f"{ei}{ns}{tf}{jp}"


def _mindset_label(growth_mindset: float) -> str:
    if growth_mindset >= 0.6:
        return "growth"
    if growth_mindset <= 0.35:
        return "fixed"
    return "mixed"


def _anxiety_level(anxiety: float) -> str:
    if anxiety > 0.65:
        return "high"
    if anxiety >= 0.35:
        return "moderate"
    return "low"


def _dominant_learning_style(depth_preference: float) -> str:
    if depth_preference > 0.6:
        return "conceptual"
    if depth_preference < 0.4:
        return "procedural"
    return "balanced"


def _psychological_readiness(growth_mindset: float, anxiety: float,
                              conscientiousness: float) -> str:
    """
    Composite readiness: high requires growth mindset, low anxiety, high conscientiousness.
    Low readiness if any dimension is severely unfavourable.
    """
    score = 0
    # Growth mindset contribution
    if growth_mindset >= 0.6:
        score += 2
    elif growth_mindset >= 0.4:
        score += 1

    # Anxiety contribution (inverse)
    if anxiety < 0.35:
        score += 2
    elif anxiety <= 0.65:
        score += 1

    # Conscientiousness contribution
    if conscientiousness >= 0.6:
        score += 2
    elif conscientiousness >= 0.4:
        score += 1

    if score >= 5:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


def _calibration_summary(calibration: list[dict]) -> CalibrationSummary:
    over = sum(
        1 for c in calibration if c["stated_high"] and c["gap"] > 0.2
    )
    under = sum(
        1 for c in calibration if not c["stated_high"] and c["gap"] < -0.2
    )
    well = len(calibration) - over - under
    return CalibrationSummary(
        overconfident=over,
        underconfident=under,
        well_calibrated=well,
    )


def _episode_counts(episodes: list[dict]) -> dict:
    counts = Counter(e["episode_type"] for e in episodes)
    # Ensure all known types present for consistent shape
    for t in ("breakthrough", "belief", "question", "struggle", "connection", "awe"):
        counts.setdefault(t, 0)
    return dict(counts)


def _bt_ratio(counts: dict) -> float:
    breakthroughs = counts.get("breakthrough", 0)
    struggles     = counts.get("struggle", 0)
    if struggles == 0:
        return float(breakthroughs) if breakthroughs > 0 else 0.0
    return round(breakthroughs / struggles, 2)


def _bmad_flags(
    psyche: dict,
    mindset_label: str,
    anxiety_level: str,
    bt_ratio: float,
    episode_counts: dict,
    calibration: CalibrationSummary,
    readiness: str,
) -> list[str]:
    flags = []

    # High anxiety + fixed mindset — belief_coach needs stronger growth framing
    anxiety_val      = psyche.get("anxiety", 0.0)
    growth_val       = psyche.get("growth_mindset", 1.0)
    if anxiety_val > 0.7 and growth_val < 0.4:
        flags.append(
            "High anxiety (%.2f) + fixed mindset (%.2f) — "
            "belief_coach needs stronger growth framing before introducing new challenges." %
            (anxiety_val, growth_val)
        )

    # Very low breakthrough-to-struggle ratio — learner is stuck
    if bt_ratio < 0.25 and episode_counts.get("struggle", 0) >= 3:
        flags.append(
            f"Breakthrough-to-struggle ratio is {bt_ratio:.2f} — learner experiencing "
            "many struggles with few breakthroughs; challenge_calibrator should reduce "
            "difficulty ceiling and increase scaffolded success opportunities."
        )

    # High overconfidence — calibration feedback needed
    if calibration.overconfident >= 3:
        flags.append(
            f"{calibration.overconfident} overconfident concepts — "
            "confidence_calibrator should introduce more diagnostic self-assessment prompts."
        )

    # Low conscientiousness — task completion risk
    conscient_val = psyche.get("conscientiousness", 1.0)
    if conscient_val < 0.35:
        flags.append(
            f"Low conscientiousness score ({conscient_val:.2f}) — "
            "session_planner should favour shorter, high-frequency sessions with "
            "immediate completion rewards."
        )

    # Few or no 'belief' and 'question' episodes — low intellectual engagement signal
    belief_q = episode_counts.get("belief", 0) + episode_counts.get("question", 0)
    total_eps = sum(episode_counts.values())
    if total_eps >= 5 and belief_q == 0:
        flags.append(
            "Zero belief or question episodes in period — "
            "inquiry_alchemist should increase open-ended 'what do you think?' prompts "
            "to surface latent curiosity."
        )

    # Insufficient psyche signal
    if psyche.get("sample_count", 0) < 10:
        flags.append(
            f"Only {psyche.get('sample_count', 0)} psyche samples — "
            "portrait reliability is low; collect more interaction data before acting on scores."
        )

    # Psychological readiness low but session volume is growing
    if readiness == "low":
        flags.append(
            "Overall psychological readiness is low — "
            "consider pacing new material more slowly and prioritising emotional safety "
            "signals before content complexity."
        )

    return flags


# ── LLM narrative ──────────────────────────────────────────────────────────────

async def _generate_narrative(portrait: PsychologicalPortrait, profile: dict) -> str:
    """
    Call the local LLM to turn the structured portrait into 150-200 words of
    prose for a teacher or guardian. Falls back to a template string on failure.
    """
    name  = profile.get("name") or portrait.learner_id
    grade = profile.get("grade", "?")

    system_msg = (
        "You are a learning psychologist writing a concise motivational portrait "
        "for a teacher or parent. Use warm, professional language. "
        "Be specific — cite actual scores and labels. 150–200 words. "
        "Do not use bullet points. Write in continuous prose."
    )
    user_msg = (
        f"Write a psychological learning portrait for {name}, Grade {grade}.\n\n"
        f"Data:\n"
        f"- MBTI proxy: {portrait.mbti_proxy}\n"
        f"- Mindset: {portrait.mindset_label} (growth_mindset score: {portrait.growth_mindset:.2f})\n"
        f"- Anxiety level: {portrait.anxiety_level} (score: {portrait.anxiety:.2f})\n"
        f"- Conscientiousness: {portrait.conscientiousness:.2f}\n"
        f"- Dominant learning style: {portrait.dominant_learning_style} "
        f"(depth_preference: {portrait.depth_preference:.2f})\n"
        f"- Psychological readiness: {portrait.psychological_readiness}\n"
        f"- Calibration — overconfident: {portrait.calibration_summary.overconfident}, "
        f"underconfident: {portrait.calibration_summary.underconfident}, "
        f"well-calibrated: {portrait.calibration_summary.well_calibrated}\n"
        f"- Episode counts: {portrait.episode_counts}\n"
        f"- Breakthrough-to-struggle ratio: {portrait.breakthrough_to_struggle_ratio:.2f}\n"
        f"- Mastery orientation: {portrait.mastery_orientation:.2f}\n"
        f"\nWrite the portrait now."
    )

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
            f"{name} (Grade {grade}) presents a {portrait.mindset_label} mindset "
            f"(growth_mindset: {portrait.growth_mindset:.2f}) with {portrait.anxiety_level} "
            f"anxiety (score: {portrait.anxiety:.2f}). "
            f"MBTI proxy: {portrait.mbti_proxy}. "
            f"Dominant learning style: {portrait.dominant_learning_style}. "
            f"Psychological readiness: {portrait.psychological_readiness}. "
            f"Breakthrough-to-struggle ratio: {portrait.breakthrough_to_struggle_ratio:.2f}. "
            f"Conscientiousness: {portrait.conscientiousness:.2f}."
        )


# ── Persistence ────────────────────────────────────────────────────────────────

async def _save_portrait(conn, portrait: PsychologicalPortrait) -> None:
    data = asdict(portrait)
    narrative = data.pop("narrative", "")
    await conn.execute(
        """INSERT INTO learner_state.lens_portraits
           (learner_id, lens, portrait, narrative, computed_at, period_start, period_end)
           VALUES ($1, 'psychological', $2, $3, now(),
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
           WHERE learner_id = $1 AND lens = 'psychological'
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


# ── Public API ─────────────────────────────────────────────────────────────────

async def compute(conn, learner_id: str, period_days: int = _WINDOW) -> tuple[PsychologicalPortrait, dict]:
    """
    Run the full Psychological Lens computation for one learner.

    Three phases to avoid holding the DB connection across the slow Ollama call:
      1. Read   — fetch all DB state (conn held briefly)
      2. Compute — pure Python, no DB
      3. Narrate — Ollama HTTP call (no conn needed; released before this)
      4. Persist — re-acquire conn to save result
    """
    log.info("psychological_lens_start", learner_id=learner_id, period_days=period_days)

    # Phase 1 — sequential DB reads (asyncpg: one op at a time per conn)
    psyche      = await _fetch_psyche(conn, learner_id)
    calibration = await _fetch_calibration(conn, learner_id)
    episodes    = await _fetch_episodes(conn, learner_id, period_days)
    profile     = await _fetch_profile(conn, learner_id)

    # Phase 2 — pure computation (no DB, no network)
    gm    = float(psyche.get("growth_mindset", 0.5))
    anx   = float(psyche.get("anxiety", 0.5))
    cons  = float(psyche.get("conscientiousness", 0.5))
    depth = float(psyche.get("depth_preference", 0.5))
    mo    = float(psyche.get("mastery_orientation", 0.5))
    ext   = float(psyche.get("extroversion", 0.5))
    tf    = float(psyche.get("thinking_feeling", 0.5))
    sc    = int(psyche.get("sample_count", 0))

    mbti      = _mbti_proxy(psyche)
    mindset   = _mindset_label(gm)
    anx_level = _anxiety_level(anx)
    style     = _dominant_learning_style(depth)
    readiness = _psychological_readiness(gm, anx, cons)
    cal_sum   = _calibration_summary(calibration)
    ep_counts = _episode_counts(episodes)
    bt_ratio  = _bt_ratio(ep_counts)
    flags     = _bmad_flags(psyche, mindset, anx_level, bt_ratio, ep_counts, cal_sum, readiness)

    portrait = PsychologicalPortrait(
        learner_id=learner_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,
        conscientiousness=round(cons, 3),
        growth_mindset=round(gm, 3),
        anxiety=round(anx, 3),
        depth_preference=round(depth, 3),
        mastery_orientation=round(mo, 3),
        extroversion=round(ext, 3),
        thinking_feeling=round(tf, 3),
        psyche_sample_count=sc,
        mbti_proxy=mbti,
        mindset_label=mindset,
        anxiety_level=anx_level,
        dominant_learning_style=style,
        psychological_readiness=readiness,
        calibration_summary=cal_sum,
        episode_counts=ep_counts,
        breakthrough_to_struggle_ratio=bt_ratio,
        bmad_flags=flags,
    )

    log.info(
        "psychological_lens_computed",
        learner_id=learner_id,
        mbti=mbti,
        mindset=mindset,
        anxiety=anx_level,
        readiness=readiness,
        flags=len(flags),
    )
    return portrait, profile


async def compute_and_save(pool, learner_id: str, period_days: int = _WINDOW) -> PsychologicalPortrait:
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

    log.info("psychological_lens_done", learner_id=learner_id, narrative_len=len(portrait.narrative))
    return portrait


async def latest(conn, learner_id: str) -> Optional[dict]:
    """Return the most recently computed portrait without recomputing."""
    return await _fetch_latest(conn, learner_id)
