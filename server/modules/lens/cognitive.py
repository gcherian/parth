"""
Cognitive Lens — longitudinal portrait of a learner's academic trajectory.

Distinct from the 15 per-message micro-agents:
  • Micro-agents fire on every message → write raw signals to DB
  • This lens reads across accumulated DB state → synthesises a portrait

Reads from:
  learner_state.knowledge           mastery posteriors (mastery_tracker output)
  learner_state.misconception_map   confirmed misconceptions (misconception_hunter)
  learner_state.kt_events           SAINT+ temporal events (elapsed_ms, lag_ms)
  learner_state.confidence_calibration  stated vs actual mastery gaps
  learner_state.profiles            grade, sessions, engagement baseline

Produces:
  CognitivePortrait dataclass  →  stored as JSONB in learner_state.lens_portraits
  narrative: str               →  LLM-generated prose (150-200 words) for
                                  guardian reports, teacher summaries, BMAD review

BMAD flags surface signals that suggest the micro-agent configuration needs
revisiting — e.g. BKT priors too conservative, misconception threshold too low.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("lens.cognitive")

# ── Thresholds ────────────────────────────────────────────────────────────────
_STRONG  = Config.MASTERY_STRONG_THRESHOLD   # 0.60
_WEAK    = Config.MASTERY_WEAK_THRESHOLD     # 0.35
_WINDOW  = 30                                # days of kt_events to analyse
_FLUENCY_FAST_MS = 8_000                     # response under 8s → procedural fluency signal


# ── Portrait dataclass ────────────────────────────────────────────────────────

@dataclass
class ConceptSummary:
    concept_id: str
    p_mastery: float
    exposures: int
    demonstrations: int


@dataclass
class MisconceptionSummary:
    concept_id: str
    description: str
    evidence_count: int
    last_seen: str


@dataclass
class RetentionProfile:
    half_life_days: Optional[float]        # estimated days before mastery decays
    fastest_forgetting: list[str]          # concept_ids with steepest decay signals
    average_lag_ms: int                    # median gap between interactions


@dataclass
class FluencyDepthProfile:
    procedural_score: float                # 0–1: high = fast correct answers
    conceptual_score: float                # 0–1: high = correct on first exposure
    assessment: str                        # human-readable label


@dataclass
class CognitivePortrait:
    learner_id: str
    computed_at: str
    period_days: int

    # Mastery landscape
    strong_concepts: list[ConceptSummary]
    developing_concepts: list[ConceptSummary]
    weak_concepts: list[ConceptSummary]
    total_concepts_seen: int

    # Growth
    mastery_growth_rate: float             # avg Δp_mastery per session
    trajectory: str                        # "accelerating" | "plateauing" | "declining" | "insufficient_data"
    zpd_target: Optional[str]             # next concept to push

    # Misconceptions
    confirmed_misconceptions: list[MisconceptionSummary]
    misconception_resolution_rate: float   # fraction resolved over window

    # Retention & fluency
    retention: RetentionProfile
    fluency_depth: FluencyDepthProfile

    # Calibration
    overconfident_concepts: list[str]      # stated high but actual low
    underconfident_concepts: list[str]     # stated low but actual high

    # BMAD feedback flags
    bmad_flags: list[str]

    # LLM-generated prose
    narrative: str = ""


# ── DB queries ────────────────────────────────────────────────────────────────

async def _fetch_knowledge(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, p_mastery, exposures, demonstrations, misconceptions,
                  last_updated
           FROM learner_state.knowledge
           WHERE learner_id = $1
           ORDER BY p_mastery DESC""",
        learner_id,
    )]


async def _fetch_misconceptions(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, misconception, count, last_seen
           FROM learner_state.misconception_map
           WHERE learner_id = $1
           ORDER BY count DESC""",
        learner_id,
    )]


async def _fetch_kt_events(conn, learner_id: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, correct, elapsed_ms, lag_ms, session_id, created_at
           FROM learner_state.kt_events
           WHERE learner_id = $1 AND created_at >= $2
           ORDER BY created_at ASC""",
        learner_id, since,
    )]


async def _fetch_calibration(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT concept_id, stated_high, actual_mastery, gap
           FROM learner_state.confidence_calibration
           WHERE learner_id = $1""",
        learner_id,
    )]


async def _fetch_profile(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT name, grade, sessions, engagement_score FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    return dict(row) if row else {}


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _classify_concepts(
    knowledge: list[dict],
) -> tuple[list[ConceptSummary], list[ConceptSummary], list[ConceptSummary]]:
    strong, developing, weak = [], [], []
    for k in knowledge:
        s = ConceptSummary(
            concept_id=k["concept_id"],
            p_mastery=round(float(k["p_mastery"]), 3),
            exposures=k["exposures"],
            demonstrations=k["demonstrations"],
        )
        if s.p_mastery >= _STRONG:
            strong.append(s)
        elif s.p_mastery < _WEAK:
            weak.append(s)
        else:
            developing.append(s)
    return strong, developing, weak


def _estimate_growth_rate(kt_events: list[dict], knowledge: list[dict]) -> tuple[float, str]:
    """
    Estimate mastery growth rate from kt_events correct/incorrect ratio over time.
    Compare first-half vs second-half success rate as trajectory signal.
    """
    if len(kt_events) < 6:
        return 0.0, "insufficient_data"

    mid = len(kt_events) // 2
    first_half  = kt_events[:mid]
    second_half = kt_events[mid:]

    def success_rate(events):
        if not events:
            return 0.0
        return sum(1 for e in events if e["correct"]) / len(events)

    rate_first  = success_rate(first_half)
    rate_second = success_rate(second_half)
    delta = rate_second - rate_first

    if delta > 0.08:
        trajectory = "accelerating"
    elif delta < -0.08:
        trajectory = "declining"
    else:
        trajectory = "plateauing"

    # Growth rate: avg p_mastery across all concepts / sessions seen
    avg_mastery = statistics.mean(float(k["p_mastery"]) for k in knowledge) if knowledge else 0.0
    return round(avg_mastery, 3), trajectory


def _retention_profile(kt_events: list[dict]) -> RetentionProfile:
    """
    Proxy for forgetting curve: concepts where lag_ms is large and correct=False
    suggest rapid forgetting. Half-life estimated from decay pattern.
    """
    if not kt_events:
        return RetentionProfile(
            half_life_days=None, fastest_forgetting=[], average_lag_ms=0
        )

    lag_values = [e["lag_ms"] for e in kt_events if e["lag_ms"] > 0]
    avg_lag_ms = int(statistics.median(lag_values)) if lag_values else 0

    # Group by concept: find those with high lag + incorrect (forgetting signal)
    concept_decay: dict[str, list[bool]] = {}
    for e in kt_events:
        if e["lag_ms"] > 86_400_000:  # lag > 1 day
            concept_decay.setdefault(e["concept_id"], []).append(e["correct"])

    forgetting = [
        cid for cid, outcomes in concept_decay.items()
        if outcomes and sum(outcomes) / len(outcomes) < 0.5
    ][:3]

    # Rough half-life: if concepts are forgotten after ~lag days, half-life ≈ lag/2
    half_life = None
    if avg_lag_ms > 0 and forgetting:
        half_life = round((avg_lag_ms / 1000 / 86400) / 2, 1)

    return RetentionProfile(
        half_life_days=half_life,
        fastest_forgetting=forgetting,
        average_lag_ms=avg_lag_ms,
    )


def _fluency_depth(kt_events: list[dict], knowledge: list[dict]) -> FluencyDepthProfile:
    """
    Procedural fluency: fast correct answers on practiced concepts.
    Conceptual depth: correct on first or second exposure (no drill needed).
    """
    if not kt_events:
        return FluencyDepthProfile(procedural_score=0.0, conceptual_score=0.0,
                                   assessment="insufficient_data")

    correct_events = [e for e in kt_events if e["correct"]]
    fast_correct = [e for e in correct_events if 0 < e["elapsed_ms"] < _FLUENCY_FAST_MS]
    procedural = len(fast_correct) / max(len(correct_events), 1)

    # Conceptual: correct on first exposure (exposures == 1 in knowledge)
    low_exposure = {k["concept_id"] for k in knowledge if k["exposures"] <= 2}
    first_exposure_correct = [e for e in correct_events if e["concept_id"] in low_exposure]
    conceptual = len(first_exposure_correct) / max(len(low_exposure), 1)
    conceptual = min(1.0, conceptual)

    if procedural >= 0.6 and conceptual >= 0.5:
        label = "strong_procedural_and_conceptual"
    elif procedural >= 0.6 and conceptual < 0.4:
        label = "strong_procedural_weak_conceptual"
    elif procedural < 0.4 and conceptual >= 0.5:
        label = "weak_procedural_strong_conceptual"
    else:
        label = "developing_both"

    return FluencyDepthProfile(
        procedural_score=round(procedural, 2),
        conceptual_score=round(conceptual, 2),
        assessment=label,
    )


def _calibration_split(calibration: list[dict]) -> tuple[list[str], list[str]]:
    over  = [c["concept_id"] for c in calibration if c["stated_high"] and c["gap"] > 0.2]
    under = [c["concept_id"] for c in calibration if not c["stated_high"] and c["gap"] < -0.2]
    return over, under


def _zpd_target(developing: list[ConceptSummary], weak: list[ConceptSummary]) -> Optional[str]:
    """Return the developing concept closest to the strong threshold — highest Δ to push."""
    if developing:
        return max(developing, key=lambda c: c.p_mastery).concept_id
    if weak:
        return max(weak, key=lambda c: c.p_mastery).concept_id
    return None


def _bmad_flags(
    knowledge: list[dict],
    kt_events: list[dict],
    misconceptions: list[dict],
    fluency: FluencyDepthProfile,
    growth_rate: float,
    trajectory: str,
) -> list[str]:
    flags = []

    # All concepts stuck in 0.35–0.60 band = BKT update rate too conservative
    if knowledge:
        near_zpd = [k for k in knowledge if _WEAK <= float(k["p_mastery"]) <= _STRONG]
        if len(near_zpd) / len(knowledge) > 0.7:
            flags.append(
                "70%+ of concepts stuck in ZPD band (0.35–0.60) — BKT learning rate "
                "may be too conservative; consider raising slip/guess priors."
            )

    # High-evidence misconceptions with no resolution
    persistent = [m for m in misconceptions if m["count"] >= 4]
    if persistent:
        names = ", ".join(m["concept_id"] for m in persistent[:2])
        flags.append(
            f"Misconceptions on [{names}] seen 4+ times without resolution — "
            "consider misconception_hunter lowering evidence_required to surface earlier."
        )

    # Declining trajectory with high session count
    if trajectory == "declining" and len(kt_events) > 20:
        flags.append(
            "Declining success rate over last 30 days despite high interaction volume — "
            "check challenge_calibrator difficulty ceiling; may be over-challenging."
        )

    # Strong procedural / weak conceptual
    if fluency.assessment == "strong_procedural_weak_conceptual":
        flags.append(
            "Strong procedural fluency, weak conceptual depth — "
            "inquiry_alchemist should increase Socratic 'why does this work?' questions."
        )

    # Very few kt_events = low engagement
    if len(kt_events) < 5:
        flags.append(
            "Fewer than 5 knowledge-tracing events in 30 days — "
            "insufficient signal for reliable portrait; check session frequency."
        )

    return flags


# ── LLM narrative ─────────────────────────────────────────────────────────────

async def _generate_narrative(portrait: CognitivePortrait, profile: dict) -> str:
    """
    Call the local LLM to turn the structured portrait into 150-200 words of
    prose for a teacher or guardian. Falls back to a template string on failure.
    """
    name  = profile.get("name") or portrait.learner_id
    grade = profile.get("grade", "?")

    strong_str = ", ".join(c.concept_id for c in portrait.strong_concepts[:3]) or "none yet"
    weak_str   = ", ".join(c.concept_id for c in portrait.weak_concepts[:3]) or "none identified"
    misc_str   = "; ".join(
        f"{m.concept_id} ({m.description[:40]})" for m in portrait.confirmed_misconceptions[:2]
    ) or "none confirmed"
    zpd        = portrait.zpd_target or "undetermined"

    system_msg = (
        "You are a learning analytics specialist writing a concise academic portrait "
        "for a teacher or parent. Use plain, warm, professional language. "
        "Be specific — cite actual concept names and numbers. 150–200 words. "
        "Do not use bullet points. Write in continuous prose."
    )
    user_msg = f"""Write a cognitive learning portrait for {name}, Grade {grade}.

Data:
- Trajectory: {portrait.trajectory} (growth rate: {portrait.mastery_growth_rate:.2f})
- Strong concepts: {strong_str}
- Weak concepts: {weak_str}
- ZPD target (next to push): {zpd}
- Confirmed misconceptions: {misc_str}
- Fluency/Depth: {portrait.fluency_depth.assessment}
- Retention half-life estimate: {portrait.retention.half_life_days or 'unknown'} days
- Overconfident on: {', '.join(portrait.overconfident_concepts[:2]) or 'none'}
- Underconfident on: {', '.join(portrait.underconfident_concepts[:2]) or 'none'}

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
            f"{name} (Grade {grade}) is on a {portrait.trajectory} trajectory. "
            f"Strong in: {strong_str}. Needs work on: {weak_str}. "
            f"ZPD target: {zpd}. "
            f"Fluency profile: {portrait.fluency_depth.assessment}. "
            f"{'Misconceptions confirmed on: ' + misc_str + '.' if portrait.confirmed_misconceptions else ''}"
        )


# ── Persistence ───────────────────────────────────────────────────────────────

async def _save_portrait(conn, portrait: CognitivePortrait) -> None:
    data = asdict(portrait)
    narrative = data.pop("narrative", "")
    await conn.execute(
        """INSERT INTO learner_state.lens_portraits
           (learner_id, lens, portrait, narrative, computed_at, period_start, period_end)
           VALUES ($1, 'cognitive', $2, $3, now(),
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
           WHERE learner_id = $1 AND lens = 'cognitive'
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

async def compute(conn, learner_id: str, period_days: int = _WINDOW) -> CognitivePortrait:
    """
    Run the full Cognitive Lens computation for one learner.

    Three phases to avoid holding the DB connection across the slow Ollama call:
      1. Read   — fetch all DB state (conn held briefly)
      2. Compute — pure Python, no DB
      3. Narrate — Ollama HTTP call (no conn needed; released before this)
      4. Persist — re-acquire conn to save result
    """
    log.info("cognitive_lens_start", learner_id=learner_id, period_days=period_days)

    # Phase 1 — sequential DB reads (asyncpg: one op at a time per conn)
    knowledge      = await _fetch_knowledge(conn, learner_id)
    misconceptions = await _fetch_misconceptions(conn, learner_id)
    kt_events      = await _fetch_kt_events(conn, learner_id, period_days)
    calibration    = await _fetch_calibration(conn, learner_id)
    profile        = await _fetch_profile(conn, learner_id)

    # Phase 2 — pure computation (no DB, no network)
    strong, developing, weak = _classify_concepts(knowledge)
    growth_rate, trajectory  = _estimate_growth_rate(kt_events, knowledge)
    retention                = _retention_profile(kt_events)
    fluency                  = _fluency_depth(kt_events, knowledge)
    overconfident, underconf = _calibration_split(calibration)
    zpd                      = _zpd_target(developing, weak)
    flags                    = _bmad_flags(knowledge, kt_events, misconceptions, fluency,
                                           growth_rate, trajectory)

    portrait = CognitivePortrait(
        learner_id=learner_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,
        strong_concepts=strong,
        developing_concepts=developing,
        weak_concepts=weak,
        total_concepts_seen=len(knowledge),
        mastery_growth_rate=growth_rate,
        trajectory=trajectory,
        zpd_target=zpd,
        confirmed_misconceptions=[
            MisconceptionSummary(
                concept_id=m["concept_id"],
                description=m["misconception"],
                evidence_count=m["count"],
                last_seen=(m["last_seen"].isoformat()
                           if hasattr(m["last_seen"], "isoformat") else str(m["last_seen"])),
            )
            for m in misconceptions
        ],
        misconception_resolution_rate=0.0,
        retention=retention,
        fluency_depth=fluency,
        overconfident_concepts=overconfident,
        underconfident_concepts=underconf,
        bmad_flags=flags,
    )

    log.info("cognitive_lens_computed", learner_id=learner_id,
             strong=len(strong), weak=len(weak), flags=len(flags))
    return portrait, profile


async def compute_and_save(pool, learner_id: str, period_days: int = _WINDOW) -> CognitivePortrait:
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

    log.info("cognitive_lens_done", learner_id=learner_id, narrative_len=len(portrait.narrative))
    return portrait


async def latest(conn, learner_id: str) -> Optional[dict]:
    """Return the most recently computed portrait without recomputing."""
    return await _fetch_latest(conn, learner_id)


# asyncio is used inside compute() via asyncio.gather — import it here
import asyncio  # noqa: E402
