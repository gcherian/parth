"""Profile read/write helpers — all Postgres, no SQLite."""
import json
from datetime import datetime

from foundation.observability import get_logger
from modules.learner_state.knowledge import weak_concepts, strong_concepts

log = get_logger("learner_state.profile")


async def get_or_create(conn, learner_id: str, name: str = "", grade: int = 6) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    if row:
        return dict(row)

    await conn.execute(
        """
        INSERT INTO learner_state.profiles (learner_id, name, grade)
        VALUES ($1, $2, $3)
        ON CONFLICT (learner_id) DO NOTHING
        """,
        learner_id, name, grade,
    )
    return {
        "learner_id": learner_id, "name": name, "grade": grade,
        "sessions": 0, "total_questions": 0, "streak_days": 0,
        "last_emotion": "neutral", "engagement_score": 5.0,
        "language_ratio": 1.0, "analogy_scores": {},
        "motivational_profile": {},
    }


async def record_question(conn, learner_id: str):
    await conn.execute(
        """
        UPDATE learner_state.profiles
        SET total_questions = total_questions + 1, last_seen = now()
        WHERE learner_id = $1
        """,
        learner_id,
    )


async def update_emotion(conn, learner_id: str, emotion: str, engagement: float):
    await conn.execute(
        """
        UPDATE learner_state.profiles
        SET last_emotion    = $2,
            engagement_score = 0.7 * engagement_score + 0.3 * $3
        WHERE learner_id = $1
        """,
        learner_id, emotion, engagement,
    )
    await conn.execute(
        """
        INSERT INTO learner_state.emotion_history (learner_id, emotion, engagement)
        VALUES ($1, $2, $3)
        """,
        learner_id, emotion, engagement,
    )


async def update_language(conn, learner_id: str, ratio_sample: float):
    await conn.execute(
        """
        UPDATE learner_state.profiles
        SET language_ratio = 0.8 * language_ratio + 0.2 * $2
        WHERE learner_id = $1
        """,
        learner_id, ratio_sample,
    )


async def update_analogy_scores(conn, learner_id: str, domains: list[str], engagement: float):
    if not domains:
        return
    row = await conn.fetchrow(
        "SELECT analogy_scores FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    scores: dict = dict(row["analogy_scores"]) if row and row["analogy_scores"] else {}
    for domain in domains:
        old = scores.get(domain, 5.0)
        scores[domain] = round(0.8 * old + 0.2 * engagement, 2)
    await conn.execute(
        "UPDATE learner_state.profiles SET analogy_scores = $2 WHERE learner_id = $1",
        learner_id, json.dumps(scores),
    )


async def update_motivational_profile(conn, learner_id: str, subject: str, engagement: float):
    row = await conn.fetchrow(
        "SELECT motivational_profile FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    profile: dict = dict(row["motivational_profile"]) if row and row["motivational_profile"] else {}
    old = profile.get(subject, 5.0)
    profile[subject] = round(0.8 * old + 0.2 * engagement, 2)
    await conn.execute(
        "UPDATE learner_state.profiles SET motivational_profile = $2 WHERE learner_id = $1",
        learner_id, json.dumps(profile),
    )


async def update_misconception_map(conn, learner_id: str, concept_id: str, misconception: str):
    existing = await conn.fetchrow(
        """
        SELECT id, count FROM learner_state.misconception_map
        WHERE learner_id = $1 AND concept_id = $2 AND misconception = $3
        """,
        learner_id, concept_id, misconception,
    )
    if existing:
        await conn.execute(
            """
            UPDATE learner_state.misconception_map
            SET count = count + 1, last_seen = now()
            WHERE id = $1
            """,
            existing["id"],
        )
    else:
        await conn.execute(
            """
            INSERT INTO learner_state.misconception_map
                (learner_id, concept_id, misconception)
            VALUES ($1, $2, $3)
            """,
            learner_id, concept_id, misconception,
        )


async def build_learner_context(
    conn, learner_id: str, profile: dict, psyche: dict | None = None
) -> str:
    from modules.learner_state.psyche import build_psyche_instructions
    from modules.krishna_oracle.oracle import get_latest_guidance, mark_applied

    emotion    = profile.get("last_emotion", "neutral")
    engagement = profile.get("engagement_score", 5.0)
    lang_ratio = profile.get("language_ratio", 1.0)

    if lang_ratio > 0.8:
        lang_str = "English"
    elif lang_ratio < 0.3:
        lang_str = "Hindi"
    else:
        lang_str = "Hindi-English mix"

    # Top 2 analogy domains
    analogy_scores: dict = profile.get("analogy_scores") or {}
    if isinstance(analogy_scores, str):
        analogy_scores = json.loads(analogy_scores)
    top_domains = sorted(analogy_scores, key=lambda k: analogy_scores[k], reverse=True)[:2]

    # High-engagement subjects
    motiv: dict = profile.get("motivational_profile") or {}
    if isinstance(motiv, str):
        motiv = json.loads(motiv)
    high_subjects = [s for s, v in sorted(motiv.items(), key=lambda x: -x[1]) if v >= 6.5][:2]

    # Recent misconceptions to watch
    misc_rows = await conn.fetch(
        """
        SELECT concept_id, misconception FROM learner_state.misconception_map
        WHERE learner_id = $1
        ORDER BY last_seen DESC
        LIMIT 2
        """,
        learner_id,
    )
    misc_lines = [f"{r['concept_id']}: {r['misconception'][:60]}" for r in misc_rows]

    # Immediate tone from emotion
    tone_map = {
        "confused":   "Child seems confused right now — use extra simple language and short steps.",
        "disengaged": "Child seems bored — open with a fun real-world hook before explaining.",
        "excited":    "Child is excited — match their energy, keep momentum.",
    }
    tone = tone_map.get(emotion, "Use warm, encouraging tone.")

    lines = [
        f"Learner: {profile.get('name','') or 'Student'}, Grade {profile.get('grade', 6)}",
        f"Current state: {emotion}, engagement {engagement:.1f}/10",
        f"Language preference: {lang_str}",
    ]
    if misc_lines:
        lines.append("Misconceptions to gently correct: " + "; ".join(misc_lines))
    if top_domains:
        lines.append("Best analogy domains: " + ", ".join(top_domains))
    if high_subjects:
        lines.append("High-engagement subjects: " + ", ".join(high_subjects))
    lines.append(tone)

    # Psyche-based pedagogical calibration
    if psyche:
        psyche_block = build_psyche_instructions(psyche)
        if psyche_block:
            lines.append(psyche_block)

    # Krishna Oracle — frontier model strategic guidance (injected once per session)
    try:
        guidance = await get_latest_guidance(conn, learner_id)
        if guidance:
            lines.append(
                "\n\nKrishna's strategic guidance for this child:\n"
                f"- Focus concept: {guidance.get('focus_concept', '')}\n"
                f"- Teaching strategy: {guidance.get('teaching_strategy', '')}\n"
                f"- Try this analogy: {guidance.get('analogy_suggestion', '')}\n"
                f"- Encourage with: \"{guidance.get('encouragement_template', '')}\"\n"
                f"- Watch out for: {guidance.get('watch_out', '')}"
            )
            await mark_applied(conn, learner_id)
    except Exception:
        pass  # Krishna guidance is optional; never block Parth

    return "\n".join(lines)
