import json
import logging
from datetime import datetime

from learner.db import get_conn

log = logging.getLogger("parth.profile")

_EMA = 0.7   # weight of history vs new observation


def get_or_create(learner_id: str, name: str = "", grade: int = 6) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM learners WHERE id=?", (learner_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO learners (id, name, grade, last_seen) VALUES (?,?,?,?)",
                (learner_id, name, grade, datetime.utcnow().isoformat()),
            )
            return _defaults(learner_id, name, grade)
        d = dict(row)
        for json_col in ("weak_topics", "misconceptions", "knowledge_state",
                         "misconception_map", "motivational_profile", "analogy_scores"):
            d[json_col] = json.loads(d.get(json_col) or "{}" if json_col not in
                                     ("weak_topics", "misconceptions") else d.get(json_col) or "[]")
        return d


def _defaults(learner_id, name, grade):
    return {
        "id": learner_id, "name": name, "grade": grade,
        "sessions": 0, "total_questions": 0,
        "weak_topics": [], "misconceptions": [],
        "knowledge_state": {}, "misconception_map": {},
        "motivational_profile": {}, "analogy_scores": {},
        "last_emotion": "neutral", "engagement_score": 5.0,
        "language_ratio": 1.0,
    }


def record_question(learner_id: str):
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE learners SET total_questions=total_questions+1, last_seen=? WHERE id=?",
                (datetime.utcnow().isoformat(), learner_id),
            )
    except Exception as e:
        log.warning(f"record_question failed: {e}")


def update_emotion(learner_id: str, emotion: str, engagement: int):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT engagement_score FROM learners WHERE id=?", (learner_id,)
            ).fetchone()
            old_score = float(row["engagement_score"] or 5.0) if row else 5.0
            new_score = round(_EMA * old_score + (1 - _EMA) * engagement, 2)
            conn.execute(
                "UPDATE learners SET last_emotion=?, engagement_score=? WHERE id=?",
                (emotion, new_score, learner_id),
            )
    except Exception as e:
        log.warning(f"update_emotion failed: {e}")


def update_language(learner_id: str, ratio_sample: float):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT language_ratio FROM learners WHERE id=?", (learner_id,)
            ).fetchone()
            old = float(row["language_ratio"] or 1.0) if row else 1.0
            new = round(0.8 * old + 0.2 * ratio_sample, 3)
            conn.execute(
                "UPDATE learners SET language_ratio=? WHERE id=?",
                (new, learner_id),
            )
    except Exception as e:
        log.warning(f"update_language failed: {e}")


def update_analogy_scores(learner_id: str, domains: list[str], engagement: int):
    """Credit or penalise domains based on child's engagement on this turn."""
    if not domains:
        return
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT analogy_scores FROM learners WHERE id=?", (learner_id,)
            ).fetchone()
            scores: dict[str, float] = json.loads(row["analogy_scores"] or "{}") if row else {}
            for domain in domains:
                old = scores.get(domain, 5.0)
                scores[domain] = round(_EMA * old + (1 - _EMA) * engagement, 2)
            conn.execute(
                "UPDATE learners SET analogy_scores=? WHERE id=?",
                (json.dumps(scores), learner_id),
            )
    except Exception as e:
        log.warning(f"update_analogy_scores failed: {e}")


def update_misconception_map(learner_id: str, concept: str, misconception: str):
    if not concept or not misconception:
        return
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT misconception_map, misconceptions FROM learners WHERE id=?",
                (learner_id,)
            ).fetchone()
            mc_map: dict = json.loads(row["misconception_map"] or "{}") if row else {}
            mc_list: list = json.loads(row["misconceptions"] or "[]") if row else []
            # structured map
            mc_map.setdefault(concept, [])
            if misconception not in mc_map[concept]:
                mc_map[concept].append(misconception)
                mc_map[concept] = mc_map[concept][-5:]   # keep last 5 per concept
            # flat list (legacy)
            if misconception not in mc_list:
                mc_list.append(misconception)
                mc_list = mc_list[-20:]
            conn.execute(
                "UPDATE learners SET misconception_map=?, misconceptions=? WHERE id=?",
                (json.dumps(mc_map), json.dumps(mc_list), learner_id),
            )
    except Exception as e:
        log.warning(f"update_misconception_map failed: {e}")


def update_motivational_profile(learner_id: str, subject: str, engagement: int):
    if not subject:
        return
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT motivational_profile FROM learners WHERE id=?", (learner_id,)
            ).fetchone()
            profile: dict = json.loads(row["motivational_profile"] or "{}") if row else {}
            old = profile.get(subject, 5.0)
            profile[subject] = round(_EMA * old + (1 - _EMA) * engagement, 2)
            conn.execute(
                "UPDATE learners SET motivational_profile=? WHERE id=?",
                (json.dumps(profile), learner_id),
            )
    except Exception as e:
        log.warning(f"update_motivational_profile failed: {e}")


def build_learner_context(profile: dict) -> str:
    """
    Produces the learner-context block injected into the system prompt.
    Kept short: 6–8 lines, no padding.
    """
    name = profile.get("name") or "the student"
    grade = profile.get("grade", 6)
    emotion = profile.get("last_emotion", "neutral")
    engagement = profile.get("engagement_score", 5.0)
    lang_ratio = float(profile.get("language_ratio") or 1.0)
    lang_pref = "English" if lang_ratio > 0.6 else ("Hindi" if lang_ratio < 0.3 else "English-Hindi mix")

    analogy_scores: dict = profile.get("analogy_scores") or {}
    top_analogies = sorted(analogy_scores, key=lambda d: analogy_scores[d], reverse=True)[:2]

    mc_map: dict = profile.get("misconception_map") or {}
    top_misconceptions = []
    for concept, mcs in mc_map.items():
        if mcs:
            top_misconceptions.append(f"{concept}: {mcs[-1]}")
    top_misconceptions = top_misconceptions[:3]

    motiv: dict = profile.get("motivational_profile") or {}
    top_topics = sorted(motiv, key=lambda t: motiv[t], reverse=True)[:2]

    lines = [
        f"Learner: {name}, Grade {grade}",
        f"Current state: {emotion}, engagement {engagement:.0f}/10",
        f"Language preference: {lang_pref}",
    ]
    if top_misconceptions:
        lines.append("Misconceptions to gently correct if relevant: " +
                     " | ".join(top_misconceptions))
    if top_analogies:
        lines.append("Best analogy domains for this child: " + ", ".join(top_analogies))
    if top_topics:
        lines.append("High-engagement subjects: " + ", ".join(top_topics))

    # Tone instruction based on emotion
    if emotion == "confused":
        lines.append("Tone: use smaller steps, simpler words, more encouragement.")
    elif emotion == "frustrated":
        lines.append("Tone: be extra warm, validate effort before explaining.")
    elif emotion == "disengaged":
        lines.append("Tone: shorter response, end with a direct hook question.")
    elif emotion == "excited":
        lines.append("Tone: match the energy, build on enthusiasm.")

    return "\n".join(lines)
