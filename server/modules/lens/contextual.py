"""
Contextual Lens — portrait of a learner's situational and environmental context.

Distinct from the 15 per-message micro-agents:
  • Micro-agents fire on every message → write raw signals to DB
  • This lens reads across accumulated DB state → synthesises a portrait

Reads from:
  learner_state.profiles             language_ratio, engagement_score, sessions,
                                     streak_days, last_seen, name, grade,
                                     analogy_scores (JSONB)
  learner_state.language_state       preferred_lang, language_ratio
  learner_state.rhythm_state         peak_hour, session_count_today,
                                     last_session_quality
  learner_state.child_agent_config   config JSONB per agent (guardian overrides)
  learner_state.child_global_config  exam_prep_mode, exam_date, session_persona
  learner_state.family_context       caregiver_lang, routines, home_supports
  learner_state.analogy_history      domain, worked, created_at

Produces:
  ContextualPortrait dataclass  →  stored as JSONB in learner_state.lens_portraits
  narrative: str                →  LLM-generated prose (150–200 words) for
                                   guardian reports, teacher summaries, BMAD review

BMAD flags surface mismatches between inferred contextual signals and the
configuration that micro-agents are running under — e.g. language_ratio
suggests Hindi-dominant usage while language_bridge.policy is set to 'english'.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("lens.contextual")

# ── Constants ─────────────────────────────────────────────────────────────────
_WINDOW = 30                        # default look-back window in days
_HINDI_DOMINANT_THRESHOLD = 0.4     # language_ratio below this = Hindi-dominant
_MIXED_THRESHOLD = 0.7              # language_ratio below this = mixed

# Hour buckets for labelling engagement windows
_HOUR_LABELS = {
    range(5, 9):   "early_morning",
    range(9, 12):  "morning",
    range(12, 14): "midday",
    range(14, 18): "afternoon",
    range(18, 21): "evening",
    range(21, 24): "night",
}


def _label_hour(hour: int) -> str:
    for r, label in _HOUR_LABELS.items():
        if hour in r:
            return label
    return "late_night"


# ── Portrait dataclasses ──────────────────────────────────────────────────────

@dataclass
class LanguageProfile:
    dominant: str           # "english" | "hindi" | "mixed"
    ratio: float            # profiles.language_ratio (1.0 = pure English, 0.0 = pure Hindi)
    preferred_lang: str     # language_state.preferred_lang
    switches_under_stress: bool  # inferred: hindi spike on low-engagement sessions


@dataclass
class SessionPattern:
    typical_hour: int           # rhythm_state.peak_hour
    peak_window_label: str      # human-readable time-of-day label
    avg_session_count_per_week: float
    streak_days: int
    last_active_days_ago: int


@dataclass
class AnalogyPerformance:
    domain: str
    attempts: int
    success_rate: float


@dataclass
class ContextualPortrait:
    learner_id: str
    computed_at: str
    period_days: int

    # Language context
    language_profile: LanguageProfile

    # Scheduling & rhythm
    session_pattern: SessionPattern

    # Analogy effectiveness by domain (top 3)
    analogy_performance: list[AnalogyPerformance]

    # Guardian configuration coverage
    guardian_config_set: list[str]   # agent names with guardian-level overrides

    # Exam pressure
    exam_pressure: bool
    exam_date: Optional[str]         # ISO date string or None
    session_persona: str             # child_global_config.session_persona

    # Home context
    home_context: dict               # caregiver_lang, routines, home_supports

    # Peak engagement window from rhythm_state
    engagement_by_time: str          # e.g. "afternoon (peak_hour=15)"

    # BMAD configuration flags
    bmad_flags: list[str]

    # LLM-generated prose
    narrative: str = ""


# ── DB fetch helpers ──────────────────────────────────────────────────────────

async def _fetch_profile(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT name, grade, sessions, streak_days, last_seen,
                  engagement_score, language_ratio, analogy_scores
           FROM learner_state.profiles
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_language_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT preferred_lang, language_ratio
           FROM learner_state.language_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_rhythm_state(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT peak_hour, session_count_today, last_session_quality
           FROM learner_state.rhythm_state
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_child_agent_config(conn, learner_id: str) -> list[dict]:
    return [dict(r) for r in await conn.fetch(
        """SELECT agent_name, config, set_by
           FROM learner_state.child_agent_config
           WHERE learner_id = $1""",
        learner_id,
    )]


async def _fetch_child_global_config(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT exam_prep_mode, exam_date, session_persona
           FROM learner_state.child_global_config
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_family_context(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        """SELECT caregiver_lang, routines, home_supports, consent_level
           FROM learner_state.family_context
           WHERE learner_id = $1""",
        learner_id,
    )
    return dict(row) if row else {}


async def _fetch_analogy_history(conn, learner_id: str, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [dict(r) for r in await conn.fetch(
        """SELECT domain, worked, created_at
           FROM learner_state.analogy_history
           WHERE learner_id = $1 AND created_at >= $2
           ORDER BY created_at DESC""",
        learner_id, since,
    )]


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _build_language_profile(
    profile: dict,
    language_state: dict,
) -> LanguageProfile:
    """
    Determine dominant language from language_ratio (1.0 = pure English).
    switches_under_stress is a heuristic: if language_state.language_ratio
    differs from profiles.language_ratio by more than 0.15, the bridge agent
    has observed code-switching relative to the baseline captured at onboarding.
    """
    # language_ratio: 1.0 = all-English, 0.0 = all-Hindi
    ratio = float(language_state.get("language_ratio") or profile.get("language_ratio") or 1.0)
    preferred_lang = language_state.get("preferred_lang") or "english"

    if ratio < _HINDI_DOMINANT_THRESHOLD:
        dominant = "hindi"
    elif ratio < _MIXED_THRESHOLD:
        dominant = "mixed"
    else:
        dominant = "english"

    # Stress-switching heuristic: profile baseline vs live language_state ratio
    profile_ratio = float(profile.get("language_ratio") or 1.0)
    live_ratio = float(language_state.get("language_ratio") or profile_ratio)
    switches_under_stress = (profile_ratio - live_ratio) > 0.15

    return LanguageProfile(
        dominant=dominant,
        ratio=round(ratio, 3),
        preferred_lang=preferred_lang,
        switches_under_stress=switches_under_stress,
    )


def _build_session_pattern(
    profile: dict,
    rhythm_state: dict,
    period_days: int,
) -> SessionPattern:
    sessions = int(profile.get("sessions") or 0)
    streak_days = int(profile.get("streak_days") or 0)
    last_seen = profile.get("last_seen")

    if last_seen is not None:
        if hasattr(last_seen, "astimezone"):
            last_seen_utc = last_seen.astimezone(timezone.utc)
        else:
            last_seen_utc = datetime.now(timezone.utc)
        last_active_days_ago = max(0, (datetime.now(timezone.utc) - last_seen_utc).days)
    else:
        last_active_days_ago = -1  # unknown

    weeks = max(period_days / 7, 1)
    avg_per_week = round(sessions / weeks, 2) if sessions > 0 else 0.0

    typical_hour = int(rhythm_state.get("peak_hour") or 15)
    peak_window_label = f"{_label_hour(typical_hour)} (peak_hour={typical_hour})"

    return SessionPattern(
        typical_hour=typical_hour,
        peak_window_label=peak_window_label,
        avg_session_count_per_week=avg_per_week,
        streak_days=streak_days,
        last_active_days_ago=last_active_days_ago,
    )


def _build_analogy_performance(analogy_history: list[dict]) -> list[AnalogyPerformance]:
    """
    Aggregate analogy_history by domain; return top 3 by success rate
    (ties broken by attempt count).
    """
    domain_stats: dict[str, list[bool]] = {}
    for row in analogy_history:
        domain = row.get("domain") or "unknown"
        worked = bool(row.get("worked", True))
        domain_stats.setdefault(domain, []).append(worked)

    results: list[AnalogyPerformance] = []
    for domain, outcomes in domain_stats.items():
        attempts = len(outcomes)
        success_rate = round(sum(outcomes) / attempts, 3) if attempts > 0 else 0.0
        results.append(AnalogyPerformance(
            domain=domain,
            attempts=attempts,
            success_rate=success_rate,
        ))

    results.sort(key=lambda x: (x.success_rate, x.attempts), reverse=True)
    return results[:3]


def _build_guardian_config_set(agent_configs: list[dict]) -> list[str]:
    """Return agent names where the override was set by a guardian (not system default)."""
    return sorted(
        row["agent_name"]
        for row in agent_configs
        if row.get("set_by") == "guardian"
    )


def _build_home_context(family_context: dict) -> dict:
    """
    Extract caregiver-visible notes from family_context.
    Routines and home_supports are stored as JSON strings in the DB.
    """
    if not family_context:
        return {}

    def _parse_json_field(value) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}

    return {
        "caregiver_lang": family_context.get("caregiver_lang") or "",
        "routines": _parse_json_field(family_context.get("routines")),
        "home_supports": _parse_json_field(family_context.get("home_supports")),
        "consent_level": int(family_context.get("consent_level") or 1),
    }


def _build_bmad_flags(
    language_profile: LanguageProfile,
    agent_configs: list[dict],
    global_config: dict,
    session_pattern: SessionPattern,
    analogy_perf: list[AnalogyPerformance],
) -> list[str]:
    flags: list[str] = []

    # ── Language mismatch ─────────────────────────────────────────────────────
    # Find language_bridge config if present
    lang_bridge_config: dict = {}
    for row in agent_configs:
        if row.get("agent_name") == "language_bridge":
            cfg = row.get("config") or {}
            lang_bridge_config = cfg if isinstance(cfg, dict) else {}
            break

    bridge_policy = lang_bridge_config.get("policy") or ""
    if (
        language_profile.dominant in ("hindi", "mixed")
        and bridge_policy == "english"
    ):
        flags.append(
            f"language_ratio={language_profile.ratio:.2f} indicates "
            f"{language_profile.dominant}-dominant usage, but "
            f"language_bridge.policy='{bridge_policy}' — mismatch; "
            "guardian config may need updating to allow code-switching."
        )

    if language_profile.switches_under_stress:
        flags.append(
            "Detected language shift toward Hindi under stress (live ratio vs "
            "baseline diverge by >0.15) — language_bridge should consider "
            "auto-switching to mixed mode during struggle episodes."
        )

    # ── Engagement / activity warnings ────────────────────────────────────────
    if session_pattern.last_active_days_ago > 7:
        flags.append(
            f"Learner last active {session_pattern.last_active_days_ago} days ago — "
            "engagement risk; consider guardian re-activation nudge."
        )

    if session_pattern.avg_session_count_per_week < 1.5:
        flags.append(
            f"Average session frequency is {session_pattern.avg_session_count_per_week:.1f}/week — "
            "below recommended 3×/week for retention; rhythm_steward pacing may be too relaxed."
        )

    if session_pattern.streak_days == 0:
        flags.append(
            "streak_days=0 — learner has no active streak; "
            "check motivational_profile for appropriate re-engagement strategy."
        )

    # ── Exam pressure with no persona adjustment ──────────────────────────────
    exam_prep = bool(global_config.get("exam_prep_mode", False))
    persona = global_config.get("session_persona") or "auto"
    if exam_prep and persona == "auto":
        flags.append(
            "exam_prep_mode=true but session_persona='auto' — "
            "consider setting persona to 'direct' or 'encouraging' for exam focus."
        )

    # ── Analogy domain gaps ───────────────────────────────────────────────────
    low_perf = [a for a in analogy_perf if a.success_rate < 0.4 and a.attempts >= 3]
    if low_perf:
        domains = ", ".join(a.domain for a in low_perf)
        flags.append(
            f"Analogy success rate <40% for domain(s): [{domains}] — "
            "transfer_weaver should rotate to higher-success domains or "
            "adjust domain difficulty for this learner."
        )

    return flags


# ── LLM narrative ─────────────────────────────────────────────────────────────

async def _generate_narrative(
    portrait: ContextualPortrait,
    profile: dict,
) -> str:
    """
    Call the local LLM to turn the structured portrait into 150–200 words of
    warm, professional prose for a teacher or guardian. Falls back to a
    template string on failure.
    """
    name  = profile.get("name") or portrait.learner_id
    grade = profile.get("grade", "?")

    lang_str = (
        f"{portrait.language_profile.dominant} (ratio={portrait.language_profile.ratio:.2f}, "
        f"preferred={portrait.language_profile.preferred_lang})"
    )
    analogy_str = (
        "; ".join(
            f"{a.domain} {a.success_rate*100:.0f}% ({a.attempts} tries)"
            for a in portrait.analogy_performance
        ) or "no analogy data"
    )
    guardian_str = (
        ", ".join(portrait.guardian_config_set) or "none — all system defaults"
    )
    home_lang = portrait.home_context.get("caregiver_lang") or "not recorded"
    exam_note = (
        f"Exam pressure active (target date: {portrait.exam_date or 'unspecified'})."
        if portrait.exam_pressure else "No current exam pressure."
    )

    system_msg = (
        "You are a learning analytics specialist writing a contextual portrait "
        "of a student for their teacher or guardian. Use warm, professional language. "
        "Be specific — cite actual numbers and observations from the data. "
        "150–200 words. Continuous prose, no bullet points."
    )
    user_msg = f"""Write a contextual learning portrait for {name}, Grade {grade}.

Data:
- Language profile: {lang_str}
- Switches to Hindi under stress: {portrait.language_profile.switches_under_stress}
- Session rhythm: {portrait.session_pattern.avg_session_count_per_week:.1f} sessions/week, \
streak={portrait.session_pattern.streak_days} days, \
last active {portrait.session_pattern.last_active_days_ago} days ago
- Peak learning window: {portrait.engagement_by_time}
- Analogy performance (top domains): {analogy_str}
- Guardian-configured agents: {guardian_str}
- Session persona: {portrait.session_persona}
- {exam_note}
- Caregiver language at home: {home_lang}

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
            f"{name} (Grade {grade}) is a {portrait.language_profile.dominant}-dominant learner "
            f"with an average of {portrait.session_pattern.avg_session_count_per_week:.1f} "
            f"sessions per week, typically active in the {portrait.engagement_by_time}. "
            f"Current streak: {portrait.session_pattern.streak_days} days. "
            f"{'Exam preparation is active. ' if portrait.exam_pressure else ''}"
            f"Analogy performance: {analogy_str}. "
            f"Guardian has configured: {guardian_str}."
        )


# ── Persistence ───────────────────────────────────────────────────────────────

async def _save_portrait(conn, portrait: ContextualPortrait) -> None:
    data = asdict(portrait)
    narrative = data.pop("narrative", "")
    await conn.execute(
        """INSERT INTO learner_state.lens_portraits
           (learner_id, lens, portrait, narrative, computed_at, period_start, period_end)
           VALUES ($1, 'contextual', $2, $3, now(),
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
           WHERE learner_id = $1 AND lens = 'contextual'
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
    conn,
    learner_id: str,
    period_days: int = _WINDOW,
) -> tuple["ContextualPortrait", dict]:
    """
    Run the full Contextual Lens computation for one learner.

    Returns (portrait, profile) so the caller can pass profile to _generate_narrative
    without re-querying the DB. The connection is NOT held across the LLM call;
    callers should release it before calling _generate_narrative.
    """
    log.info("contextual_lens_start", learner_id=learner_id, period_days=period_days)

    # Phase 1 — sequential DB reads (asyncpg: one operation per conn at a time)
    profile        = await _fetch_profile(conn, learner_id)
    language_state = await _fetch_language_state(conn, learner_id)
    rhythm_state   = await _fetch_rhythm_state(conn, learner_id)
    agent_configs  = await _fetch_child_agent_config(conn, learner_id)
    global_config  = await _fetch_child_global_config(conn, learner_id)
    family_context = await _fetch_family_context(conn, learner_id)
    analogy_history = await _fetch_analogy_history(conn, learner_id, period_days)

    # Phase 2 — pure computation (no DB, no network)
    language_profile   = _build_language_profile(profile, language_state)
    session_pattern    = _build_session_pattern(profile, rhythm_state, period_days)
    analogy_perf       = _build_analogy_performance(analogy_history)
    guardian_config_set = _build_guardian_config_set(agent_configs)
    home_context       = _build_home_context(family_context)

    exam_pressure  = bool(global_config.get("exam_prep_mode", False))
    exam_date_raw  = global_config.get("exam_date")
    exam_date_str  = (
        exam_date_raw.isoformat()
        if exam_date_raw and hasattr(exam_date_raw, "isoformat")
        else (str(exam_date_raw) if exam_date_raw else None)
    )
    session_persona = global_config.get("session_persona") or "auto"

    peak_hour = int(rhythm_state.get("peak_hour") or 15)
    engagement_by_time = f"{_label_hour(peak_hour)} (peak_hour={peak_hour})"

    flags = _build_bmad_flags(
        language_profile,
        agent_configs,
        global_config,
        session_pattern,
        analogy_perf,
    )

    portrait = ContextualPortrait(
        learner_id=learner_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,
        language_profile=language_profile,
        session_pattern=session_pattern,
        analogy_performance=analogy_perf,
        guardian_config_set=guardian_config_set,
        exam_pressure=exam_pressure,
        exam_date=exam_date_str,
        session_persona=session_persona,
        home_context=home_context,
        engagement_by_time=engagement_by_time,
        bmad_flags=flags,
    )

    log.info(
        "contextual_lens_computed",
        learner_id=learner_id,
        dominant_lang=language_profile.dominant,
        streak=session_pattern.streak_days,
        flags=len(flags),
    )
    return portrait, profile


async def compute_and_save(
    pool,
    learner_id: str,
    period_days: int = _WINDOW,
) -> "ContextualPortrait":
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
    # conn released here — before the slow Ollama call

    # Phase 3: LLM narrative — no DB connection held during this
    portrait.narrative = await _generate_narrative(portrait, profile)

    # Phase 4: persist
    async with pool.acquire() as conn2:
        try:
            await _save_portrait(conn2, portrait)
        except Exception as exc:
            log.warning("portrait_save_failed", error=str(exc))

    log.info(
        "contextual_lens_done",
        learner_id=learner_id,
        narrative_len=len(portrait.narrative),
    )
    return portrait


async def latest(conn, learner_id: str) -> Optional[dict]:
    """Return the most recently computed portrait without recomputing."""
    return await _fetch_latest(conn, learner_id)
