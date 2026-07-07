"""Product-facing learner dimensions.

The runtime harness is made of agents. The product portrait is made of learner
dimensions. Keeping those separate lets us represent direct signals, derived
signals, proxies, and reflection-backed dimensions honestly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _clamp(value: float | None, lo: float = 0.0, hi: float = 1.0) -> float | None:
    if value is None:
        return None
    return round(max(lo, min(hi, float(value))), 3)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _round_or_none(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _dimension(
    *,
    number: int,
    key: str,
    label: str,
    status: str,
    score: float | None,
    confidence: float,
    primary_agents: list[str],
    evidence: dict[str, Any],
    summary: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "number": number,
        "key": key,
        "label": label,
        "status": status,
        "score": _clamp(score),
        "confidence": _clamp(confidence) or 0.0,
        "primary_agents": primary_agents,
        "evidence": evidence,
        "summary": summary,
        "next_action": next_action,
    }


async def _fetchrow(conn, sql: str, *args) -> Any:
    try:
        return await conn.fetchrow(sql, *args)
    except Exception:
        return None


async def _fetchval(conn, sql: str, *args) -> Any:
    try:
        return await conn.fetchval(sql, *args)
    except Exception:
        return None


def build_dimension_payload(rows: dict[str, Any], learner_id: str) -> dict[str, Any]:
    """Pure snapshot synthesis from already-loaded DB rows."""
    portrait = _as_dict(_row_get(rows.get("puzzle_portrait"), "portrait_json", {}))
    puzzle_stats = rows.get("puzzle_stats")
    puzzle_count = int(_row_get(puzzle_stats, "count", 0) or 0)
    avg_quality = _round_or_none(_row_get(puzzle_stats, "avg_quality"), 3)
    deeper_rate = _round_or_none(_row_get(puzzle_stats, "deeper_rate"), 3)
    cognitive_score = None
    if avg_quality is not None:
        cognitive_score = (avg_quality / 3.0) * 0.75 + (deeper_rate or 0.0) * 0.25
    cognitive_conf = min(1.0, (puzzle_count / 5.0) * float(portrait.get("confidence", 0.0) or 0.0) + (0.12 if puzzle_count else 0.0))

    affect = rows.get("affect")
    curiosity_threads = _as_list(_row_get(rows.get("curiosity"), "threads_json", "[]"))
    open_loop_count = int(_row_get(rows.get("open_loops"), "count", 0) or 0)
    curiosity_heat = max([float(t.get("heat", 0.0) or 0.0) for t in curiosity_threads] or [0.0])
    curiosity_score = (
        float(_row_get(affect, "curiosity", 0.2) or 0.2) * 0.45
        + min(1.0, curiosity_heat) * 0.35
        + min(1.0, open_loop_count / 3.0) * 0.20
    )

    rhythm = rows.get("rhythm")
    last_quality = float(_row_get(rhythm, "last_session_quality", 0.0) or 0.0)
    sessions_today = int(_row_get(rhythm, "session_count_today", 0) or 0)
    attention_score = (last_quality / 10.0) if rhythm else None
    if attention_score is not None and sessions_today > 3:
        attention_score *= 0.82

    memory = rows.get("memory")
    due_cards = int(_row_get(memory, "due_cards", 0) or 0)
    total_cards = int(_row_get(memory, "total_cards", 0) or 0)
    episode_count = int(_row_get(memory, "episode_count", 0) or 0)
    memory_score = None
    if total_cards or episode_count:
        review_health = 1.0 - min(1.0, due_cards / max(total_cards, 1))
        episodic = min(1.0, episode_count / 5.0)
        memory_score = review_health * 0.65 + episodic * 0.35

    velocity = rows.get("velocity")
    velocity_score = _round_or_none(_row_get(velocity, "velocity_score"))
    velocity_conf = float(_row_get(velocity, "confidence", 0.0) or 0.0)

    knowledge = rows.get("knowledge")
    concept_count = int(_row_get(knowledge, "concept_count", 0) or 0)
    avg_mastery = _round_or_none(_row_get(knowledge, "avg_mastery"))
    strong_count = int(_row_get(knowledge, "strong_count", 0) or 0)
    weak_count = int(_row_get(knowledge, "weak_count", 0) or 0)

    challenge = rows.get("challenge")
    misconception = rows.get("misconception")
    misconception_count = int(_row_get(misconception, "misconception_count", 0) or 0)
    difficulty = float(_row_get(challenge, "difficulty_level", 0.5) or 0.5)
    struggles = int(_row_get(challenge, "consecutive_struggles", 0) or 0)
    problem_solving_score = None
    if challenge or misconception_count:
        problem_solving_score = max(0.0, min(1.0, difficulty * 0.55 + (1.0 - min(1.0, struggles / 4.0)) * 0.25 + (1.0 - min(1.0, misconception_count / 8.0)) * 0.20))

    pattern = rows.get("pattern")
    creativity = rows.get("creativity")
    pattern_message = str(_row_get(pattern, "latest_pattern_message", "") or "")
    creative_episode_count = int(_row_get(creativity, "creative_episode_count", 0) or 0)
    creativity_score = None
    if pattern_message or creative_episode_count:
        creativity_score = min(1.0, (0.45 if pattern_message else 0.0) + creative_episode_count / 6.0)

    drive = rows.get("drive")
    drive_score = _round_or_none(_row_get(drive, "drive_score"))
    drive_conf = float(_row_get(drive, "confidence", 0.0) or 0.0)

    family = rows.get("family")
    frustration = float(_row_get(affect, "frustration", 0.1) or 0.1)
    confusion = float(_row_get(affect, "confusion", 0.15) or 0.15)
    boredom = float(_row_get(affect, "boredom", 0.1) or 0.1)
    delight = float(_row_get(affect, "delight", 0.1) or 0.1)
    wellbeing_score = max(0.0, min(1.0, 0.55 + delight * 0.25 + float(_row_get(affect, "curiosity", 0.2) or 0.2) * 0.20 - frustration * 0.25 - confusion * 0.15 - boredom * 0.15))
    family_context_available = bool(family and int(_row_get(family, "consent_level", 1) or 1) >= 2)

    psyche = rows.get("psyche")
    confidence_row = rows.get("confidence")
    avg_gap = abs(float(_row_get(confidence_row, "avg_gap", 0.0) or 0.0))
    calibration_count = int(_row_get(confidence_row, "calibration_count", 0) or 0)
    growth = float(_row_get(psyche, "growth_mindset", 0.5) or 0.5)
    anxiety = float(_row_get(psyche, "anxiety", 0.5) or 0.5)
    confidence_score = max(0.0, min(1.0, growth * 0.45 + (1.0 - anxiety) * 0.25 + (1.0 - min(1.0, avg_gap)) * 0.30))
    confidence_conf = min(1.0, (int(_row_get(psyche, "sample_count", 0) or 0) / 8.0) * 0.65 + (calibration_count / 4.0) * 0.35)

    resilience_score = None
    if challenge or drive:
        return_after = _row_get(drive, "return_after_difficulty")
        return_after = 0.5 if return_after is None else float(return_after)
        resilience_score = max(0.0, min(1.0, return_after * 0.45 + (1.0 - min(1.0, struggles / 4.0)) * 0.30 + difficulty * 0.25))

    language = rows.get("language")
    register = rows.get("register")
    profile = rows.get("profile")
    analogy_scores = _as_dict(_row_get(profile, "analogy_scores", {}))
    learning_pref_conf = min(
        1.0,
        (0.25 if language else 0.0)
        + (0.25 if register else 0.0)
        + (0.25 if analogy_scores else 0.0)
        + min(0.25, puzzle_count / 20.0),
    )

    value = rows.get("value")
    purpose_themes = _as_dict(_row_get(value, "purpose_themes", {}))
    values_json = _as_list(_row_get(value, "values_json", []))
    value_conf = float(_row_get(value, "confidence", 0.0) or 0.0)

    social = rows.get("social")
    social_count = int(_row_get(social, "sample_count", 0) or 0)
    social_conf = min(1.0, social_count / 5.0)
    social_prefs = {
        "group": _round_or_none(_row_get(social, "group_preference", 0.5)),
        "solo": _round_or_none(_row_get(social, "solo_preference", 0.5)),
        "teach_back": _round_or_none(_row_get(social, "teach_back_preference", 0.5)),
    }

    dimensions = [
        _dimension(
            number=1,
            key="cognitive_ability",
            label="Cognitive Ability",
            status="direct",
            score=cognitive_score,
            confidence=cognitive_conf,
            primary_agents=["puzzle_engine"],
            evidence={
                "cold_start_probes_completed": puzzle_count,
                "avg_quality_0_3": avg_quality,
                "deeper_rate": deeper_rate,
                "primary_sphere": portrait.get("primary_sphere", ""),
            },
            summary="Domain-general cold-start puzzle reasoning before subject tutoring.",
            next_action="Complete all five cold-start probes before using this for placement.",
        ),
        _dimension(
            number=2,
            key="curiosity_exploration",
            label="Curiosity and Exploration",
            status="derived",
            score=curiosity_score,
            confidence=min(1.0, 0.25 + len(curiosity_threads) * 0.18 + open_loop_count * 0.12),
            primary_agents=["inquiry_alchemist", "pattern_creation_guide", "emotion_compass"],
            evidence={
                "curiosity_probability": _round_or_none(_row_get(affect, "curiosity")),
                "live_threads": len(curiosity_threads),
                "open_wonder_questions": open_loop_count,
            },
            summary="Live curiosity threads, wonder questions, and real-time curiosity probability.",
            next_action="Ask an open why/how question and watch for unprompted returns.",
        ),
        _dimension(
            number=3,
            key="attention_focus",
            label="Attention and Focus",
            status="derived",
            score=attention_score,
            confidence=0.65 if rhythm else 0.0,
            primary_agents=["rhythm_time_steward"],
            evidence={
                "peak_hour": _row_get(rhythm, "peak_hour"),
                "sessions_today": sessions_today,
                "last_session_quality": _round_or_none(last_quality),
            },
            summary="Peak-focus hour and fatigue/pacing estimate.",
            next_action="Collect a few sessions at different times of day.",
        ),
        _dimension(
            number=4,
            key="memory_retention",
            label="Memory and Retention",
            status="direct",
            score=memory_score,
            confidence=min(1.0, total_cards / 8.0 + episode_count / 12.0),
            primary_agents=["memory_keeper"],
            evidence={"practice_cards": total_cards, "due_cards": due_cards, "episodes": episode_count},
            summary="SM-2 review health plus episodic learning moments.",
            next_action="Create review cards through demonstrated concepts and revisit due cards.",
        ),
        _dimension(
            number=5,
            key="learning_velocity",
            label="Learning Velocity",
            status="derived",
            score=velocity_score,
            confidence=velocity_conf,
            primary_agents=["learning_velocity", "mastery_tracker"],
            evidence={
                "zpd_distance": _round_or_none(_row_get(velocity, "zpd_distance")),
                "time_to_mastery_turns": _round_or_none(_row_get(velocity, "time_to_mastery_turns"), 1),
                "sample_size": _row_get(velocity, "sample_size", 0),
            },
            summary="Time-to-mastery estimate normalized by MasteryTracker ZPD distance.",
            next_action="Needs several concept exposures before it stabilizes.",
        ),
        _dimension(
            number=6,
            key="conceptual_depth",
            label="Conceptual Understanding and Depth",
            status="direct",
            score=avg_mastery,
            confidence=min(1.0, concept_count / 8.0),
            primary_agents=["mastery_tracker"],
            evidence={"concept_count": concept_count, "strong_count": strong_count, "weak_count": weak_count},
            summary="Per-concept BKT-style mastery within taught material.",
            next_action="Keep concept tagging active in chat and practice.",
        ),
        _dimension(
            number=7,
            key="problem_solving_critical_thinking",
            label="Problem Solving and Critical Thinking",
            status="proxy",
            score=problem_solving_score,
            confidence=min(1.0, 0.25 + misconception_count / 10.0 + (0.35 if challenge else 0.0)),
            primary_agents=["challenge_calibrator", "misconception_hunter"],
            evidence={"difficulty_level": _round_or_none(difficulty), "struggle_streak": struggles, "misconceptions": misconception_count},
            summary="Proxy from productive struggle and flawed-reasoning detection.",
            next_action="Add direct puzzle/problem-solving rubric before high-stakes use.",
        ),
        _dimension(
            number=8,
            key="creativity_imagination",
            label="Creativity and Imagination",
            status="proxy",
            score=creativity_score,
            confidence=min(1.0, (0.35 if pattern_message else 0.0) + creative_episode_count / 8.0),
            primary_agents=["pattern_creation_guide"],
            evidence={"latest_pattern_message": pattern_message[:120], "connection_or_awe_episodes": creative_episode_count},
            summary="Proxy from cross-domain connections and pattern/awe moments.",
            next_action="Add an explicit open-ended creation/reflection prompt.",
        ),
        _dimension(
            number=9,
            key="motivation_drive",
            label="Motivation and Drive",
            status="derived",
            score=drive_score,
            confidence=drive_conf,
            primary_agents=["motivation_drive"],
            evidence={
                "return_after_difficulty": _round_or_none(_row_get(drive, "return_after_difficulty")),
                "active_days_14": _row_get(drive, "active_days_14", 0),
                "hard_return_count": _row_get(drive, "hard_return_count", 0),
            },
            summary="Voluntary-return cadence under difficulty, not generic engagement.",
            next_action="Needs multi-day usage to become meaningful.",
        ),
        _dimension(
            number=10,
            key="wellbeing_family_environment",
            label="Emotional Well Being and Family Environment",
            status="derived",
            score=wellbeing_score,
            confidence=min(1.0, (0.55 if affect else 0.0) + (0.25 if family else 0.0)),
            primary_agents=["emotion_compass", "family_alliance"],
            evidence={
                "affect": {
                    "frustration": _round_or_none(frustration),
                    "confusion": _round_or_none(confusion),
                    "boredom": _round_or_none(boredom),
                    "curiosity": _round_or_none(_row_get(affect, "curiosity")),
                    "delight": _round_or_none(delight),
                },
                "family_context_available": family_context_available,
                "consent_level": _row_get(family, "consent_level", 0),
            },
            summary="Affect vector plus consent-gated home context kept separate in evidence.",
            next_action="Invite guardian context only with explicit consent.",
        ),
        _dimension(
            number=11,
            key="confidence_self_efficacy",
            label="Confidence and Self Efficacy",
            status="direct",
            score=confidence_score,
            confidence=confidence_conf,
            primary_agents=["belief_coach"],
            evidence={"growth_mindset": _round_or_none(growth), "anxiety": _round_or_none(anxiety), "avg_confidence_gap": _round_or_none(avg_gap)},
            summary="Confidence-vs-mastery calibration and growth-mindset state.",
            next_action="Ask for confidence before/after a few solved problems.",
        ),
        _dimension(
            number=12,
            key="adaptability_resilience",
            label="Adaptability and Resilience",
            status="proxy",
            score=resilience_score,
            confidence=min(1.0, (0.4 if challenge else 0.0) + drive_conf * 0.6),
            primary_agents=["challenge_calibrator", "motivation_drive"],
            evidence={"difficulty_level": _round_or_none(difficulty), "struggle_streak": struggles, "return_after_difficulty": _round_or_none(_row_get(drive, "return_after_difficulty"))},
            summary="Proxy from productive-failure tolerance and returning after hard turns.",
            next_action="Use explicit reflection after a hard problem for a direct resilience signal.",
        ),
        _dimension(
            number=13,
            key="learning_preference",
            label="Learning Preference",
            status="derived",
            score=None,
            confidence=learning_pref_conf,
            primary_agents=["register_tuner", "language_bridge", "transfer_weaver"],
            evidence={
                "language": _row_get(language, "preferred_lang"),
                "language_ratio": _round_or_none(_row_get(language, "language_ratio")),
                "sentence_length_pref": _row_get(register, "sentence_length_pref"),
                "formality": _round_or_none(_row_get(register, "formality")),
                "analogy_scores": analogy_scores,
            },
            summary="Tone, language mix, and domain anchors; not a VARK modality classifier.",
            next_action="Use this descriptively; avoid labeling the child as one fixed type.",
        ),
        _dimension(
            number=14,
            key="value_purpose",
            label="Value and Purpose",
            status="reflection",
            score=None,
            confidence=value_conf,
            primary_agents=["value_purpose_reflection"],
            evidence={"purpose_themes": purpose_themes, "values": values_json, "sample_count": _row_get(value, "sample_count", 0)},
            summary="Periodic open-ended reflection synthesized separately from chat micro-signals.",
            next_action="Ask the next reflection prompt when cadence allows.",
        ),
        _dimension(
            number=15,
            key="social_learning_collaboration",
            label="Social Learning and Collaboration",
            status="direct",
            score=None,
            confidence=social_conf,
            primary_agents=["social_preference"],
            evidence={**social_prefs, "sample_count": social_count, "last_signal": _row_get(social, "last_signal", "")},
            summary="Group vs solo vs teach-back preference from collaboration language.",
            next_action="Offer optional teach-back or peer-style prompts, never forced sharing.",
        ),
    ]

    ready = sum(1 for d in dimensions if d["confidence"] >= 0.35)
    direct = sum(1 for d in dimensions if d["status"] == "direct")
    proxy = [d["key"] for d in dimensions if d["status"] == "proxy"]
    low_confidence = [d["key"] for d in dimensions if d["confidence"] < 0.2]

    return {
        "learner_id": learner_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mvp_status": {
            "dimensions_ready": ready,
            "total_dimensions": len(dimensions),
            "direct_dimensions": direct,
            "proxy_dimensions": proxy,
            "low_confidence_dimensions": low_confidence,
        },
        "dimensions": dimensions,
    }


async def build_dimension_snapshot(conn, learner_id: str) -> dict[str, Any]:
    """Load all evidence and synthesize the current 15-dimension snapshot."""
    rows = {
        "profile": await _fetchrow(conn, "SELECT analogy_scores FROM learner_state.profiles WHERE learner_id=$1", learner_id),
        "puzzle_portrait": await _fetchrow(conn, "SELECT portrait_json FROM puzzle_engine.portraits WHERE learner_id=$1", learner_id),
        "puzzle_stats": await _fetchrow(
            conn,
            """SELECT COUNT(*)::int AS count,
                      AVG(quality)::float AS avg_quality,
                      AVG(CASE WHEN reached_deeper THEN 1.0 ELSE 0.0 END)::float AS deeper_rate
               FROM puzzle_engine.responses
               WHERE learner_id=$1""",
            learner_id,
        ),
        "affect": await _fetchrow(conn, "SELECT * FROM learner_state.affect_state WHERE learner_id=$1", learner_id),
        "curiosity": await _fetchrow(
            conn,
            """SELECT threads_json FROM learner_state.curiosity_sessions
               WHERE learner_id=$1
               ORDER BY updated_at DESC
               LIMIT 1""",
            learner_id,
        ),
        "open_loops": {"count": await _fetchval(conn, "SELECT COUNT(*) FROM learner_state.open_loops WHERE learner_id=$1 AND status='open'", learner_id) or 0},
        "rhythm": await _fetchrow(conn, "SELECT * FROM learner_state.rhythm_state WHERE learner_id=$1", learner_id),
        "memory": await _fetchrow(
            conn,
            """SELECT
                    (SELECT COUNT(*) FROM practice_engine.cards WHERE learner_id=$1)::int AS total_cards,
                    (SELECT COUNT(*) FROM practice_engine.cards WHERE learner_id=$1 AND next_review < now())::int AS due_cards,
                    (SELECT COUNT(*) FROM learner_state.episodes WHERE learner_id=$1)::int AS episode_count""",
            learner_id,
        ),
        "velocity": await _fetchrow(conn, "SELECT * FROM learner_state.learning_velocity_state WHERE learner_id=$1", learner_id),
        "knowledge": await _fetchrow(
            conn,
            """SELECT COUNT(*)::int AS concept_count,
                      AVG(p_mastery)::float AS avg_mastery,
                      SUM(CASE WHEN p_mastery >= 0.75 THEN 1 ELSE 0 END)::int AS strong_count,
                      SUM(CASE WHEN p_mastery < 0.50 THEN 1 ELSE 0 END)::int AS weak_count
               FROM learner_state.knowledge
               WHERE learner_id=$1""",
            learner_id,
        ),
        "challenge": await _fetchrow(conn, "SELECT * FROM learner_state.challenge_state WHERE learner_id=$1", learner_id),
        "misconception": {"misconception_count": await _fetchval(conn, "SELECT COUNT(*) FROM learner_state.misconception_map WHERE learner_id=$1", learner_id) or 0},
        "pattern": await _fetchrow(conn, "SELECT * FROM learner_state.pattern_state WHERE learner_id=$1", learner_id),
        "creativity": {"creative_episode_count": await _fetchval(conn, "SELECT COUNT(*) FROM learner_state.episodes WHERE learner_id=$1 AND episode_type IN ('connection','awe')", learner_id) or 0},
        "drive": await _fetchrow(conn, "SELECT * FROM learner_state.motivation_drive_state WHERE learner_id=$1", learner_id),
        "family": await _fetchrow(conn, "SELECT * FROM learner_state.family_context WHERE learner_id=$1", learner_id),
        "psyche": await _fetchrow(conn, "SELECT * FROM learner_state.psyche WHERE learner_id=$1", learner_id),
        "confidence": await _fetchrow(
            conn,
            """SELECT COUNT(*)::int AS calibration_count, AVG(ABS(gap))::float AS avg_gap
               FROM learner_state.confidence_calibration
               WHERE learner_id=$1""",
            learner_id,
        ),
        "language": await _fetchrow(conn, "SELECT * FROM learner_state.language_state WHERE learner_id=$1", learner_id),
        "register": await _fetchrow(conn, "SELECT * FROM learner_state.register_state WHERE learner_id=$1", learner_id),
        "value": await _fetchrow(conn, "SELECT * FROM learner_state.value_purpose_state WHERE learner_id=$1", learner_id),
        "social": await _fetchrow(conn, "SELECT * FROM learner_state.social_learning_state WHERE learner_id=$1", learner_id),
    }
    return build_dimension_payload(rows, learner_id)


async def save_dimension_snapshot(conn, learner_id: str, snapshot: dict[str, Any]) -> None:
    await conn.execute(
        """INSERT INTO learner_state.dimension_snapshots
           (learner_id, snapshot_json, updated_at)
           VALUES ($1,$2,now())
           ON CONFLICT (learner_id) DO UPDATE
           SET snapshot_json=$2, updated_at=now()""",
        learner_id,
        snapshot,
    )
