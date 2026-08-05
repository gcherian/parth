"""
Teacher feedback API — no student login required.

Flow:
  Static link: /teacher/form  (no ?code= needed)
  Teacher enters their phone number, student name, grade, and subject.
  Portrait is keyed on (teacher_phone, student_name, subject).
  student_code is optional — if provided, we resolve it to a learner_id so
  Parth can inject the portrait into chat context automatically.
  Without a code, portraits are still stored and can be matched later when
  the student's learner_id is linked to the teacher's phone.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from foundation.db import get_pool
from foundation.observability import get_logger
from modules.survey.routes import verify_survey_token, mark_survey_link_opened

log = get_logger("teacher.routes")

router = APIRouter(prefix="/teacher", tags=["teacher"])


# ── Pydantic model ────────────────────────────────────────────────────────────

class TeacherFeedbackRequest(BaseModel):
    teacher_phone:      str
    teacher_name:       str
    student_name:       str
    student_grade:      Optional[str] = None
    school:             Optional[str] = None
    student_code:       Optional[str] = None   # optional join code
    subject:            str
    teacher_duration:   Optional[str] = None
    learning_style:     Optional[list[str]] = None
    pace:               Optional[str] = None
    attention:          Optional[str] = None
    work_preference:    Optional[str] = None
    question_frequency: Optional[str] = None
    error_response:     Optional[str] = None
    confidence:         Optional[int] = None
    motivation:         Optional[list[str]] = None
    performance:        Optional[str] = None
    weak_topics:        Optional[list[str]] = None
    misconceptions:     Optional[str] = None
    home_language:      Optional[str] = None
    home_support:       Optional[str] = None
    parent_involvement: Optional[str] = None
    study_time:         Optional[str] = None
    excitement:         Optional[str] = None
    teacher_insight:    Optional[str] = None
    special_needs:      Optional[str] = None
    submitted_at:       Optional[str] = None
    survey_token:       Optional[str] = None   # from a /survey/link invitation, if any


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/form")
async def teacher_form(token: Optional[str] = None):
    if token:
        claims = await verify_survey_token(token)
        if claims:
            await mark_survey_link_opened(token)
    return FileResponse("static/teacher_form.html")


@router.post("/feedback")
async def submit_feedback(body: TeacherFeedbackRequest):
    phone = body.teacher_phone.strip()
    if len(phone) < 6:
        raise HTTPException(status_code=422, detail="teacher_phone too short")
    if not body.student_name.strip():
        raise HTTPException(status_code=422, detail="student_name required")

    school_id = None
    if body.survey_token:
        claims = await verify_survey_token(body.survey_token)
        if claims:
            school_id = claims.get("school_id")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try to resolve student_code → learner_id if code was given
        learner_id = None
        if body.student_code:
            code = body.student_code.upper().strip()
            learner_row = await conn.fetchrow(
                "SELECT learner_id FROM learner_state.profiles "
                "WHERE UPPER(SUBSTR(learner_id, 1, 8)) = $1",
                code,
            )
            learner_id = learner_row["learner_id"] if learner_row else None

        payload = body.model_dump(exclude={
            "teacher_phone", "teacher_name", "student_name",
            "student_grade", "school", "student_code", "subject",
            "survey_token",
        })

        await conn.execute(
            """
            INSERT INTO teacher.portraits
                (teacher_phone, teacher_name, student_name, student_grade,
                 school, student_code, learner_id, subject, payload, submitted_at, school_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, now(), $10)
            ON CONFLICT (teacher_phone, student_name, subject) DO UPDATE
                SET teacher_name  = $2,
                    student_grade = COALESCE($4, teacher.portraits.student_grade),
                    school        = COALESCE($5, teacher.portraits.school),
                    student_code  = COALESCE($6, teacher.portraits.student_code),
                    learner_id    = COALESCE($7, teacher.portraits.learner_id),
                    payload       = $9::jsonb,
                    submitted_at  = now(),
                    school_id     = COALESCE($10, teacher.portraits.school_id)
            """,
            phone, body.teacher_name, body.student_name.strip(),
            body.student_grade, body.school,
            body.student_code.upper() if body.student_code else None,
            learner_id, body.subject, json.dumps(payload), school_id,
        )

        log.info("teacher_portrait_saved",
                 teacher_phone=phone[-4:],   # log only last 4 digits
                 student=body.student_name,
                 subject=body.subject,
                 learner_id=learner_id,
                 school_id=school_id)

    return {"status": "ok", "learner_id": learner_id}


# ── Portrait context builder — called by learner_state module ────────────────

def _staleness_note(submitted_at) -> str:
    """Same decay thinking as the BKT/SM-2 curves elsewhere in learner_state
    (see modules/practice_engine's ease_factor/interval_days, modules/lens/
    cognitive.py's half-life estimate): an old, unconfirmed observation
    should read with less certainty than a fresh one, not be asserted flatly
    forever. Scoped narrowly to this one function, not a general staleness
    framework — see server/CONVENTIONS.md's closing note on that distinction.
    """
    if submitted_at is None:
        return ""
    now = datetime.now(timezone.utc)
    age_days = (now - submitted_at).days
    if age_days < 30:
        return ""
    if age_days < 90:
        return f" (observed ~{age_days // 7} weeks ago)"
    return f" (observed ~{age_days // 30} months ago — may be outdated; confirm before relying on it heavily)"


async def get_teacher_portrait_context(conn, learner_id: str) -> str:
    """
    Return a compact teacher portrait string for injection into the tutor prompt.
    Returns empty string if no portraits have been linked to this learner_id.
    """
    rows = await conn.fetch(
        """
        SELECT teacher_name, subject, payload, submitted_at
        FROM teacher.portraits
        WHERE learner_id = $1
        ORDER BY submitted_at DESC
        """,
        learner_id,
    )
    if not rows:
        return ""

    parts = ["[Teacher Portrait — shared privately by this student's teachers]"]
    for row in rows:
        p = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        subj = row["subject"].capitalize()
        lines = [f"Subject: {subj} (from {row['teacher_name']}){_staleness_note(row['submitted_at'])}"]

        if p.get("performance"):
            lines.append(f"Performance: {p['performance'].replace('_', ' ')}")
        if p.get("learning_style"):
            lines.append(f"Learning style: {', '.join(p['learning_style'])}")
        if p.get("pace"):
            lines.append(f"Pace: {p['pace']}")
        if p.get("attention"):
            lines.append(f"Attention: {p['attention']}")
        if p.get("question_frequency"):
            lines.append(f"Asks questions: {p['question_frequency']}")
        if p.get("error_response"):
            lines.append(f"Response to mistakes: {p['error_response'].replace('_', ' ')}")
        if p.get("confidence") is not None:
            lines.append(f"Confidence level: {p['confidence']}/5")
        if p.get("motivation"):
            lines.append(f"Motivated by: {', '.join(p['motivation'])}")
        if p.get("weak_topics"):
            lines.append(f"Weak topics: {', '.join(p['weak_topics'])}")
        if p.get("misconceptions"):
            lines.append(f"Known misconceptions: {p['misconceptions']}")
        if p.get("home_language"):
            lines.append(f"Home language: {p['home_language']}")
        if p.get("home_support"):
            lines.append(f"Home support: {p['home_support'].replace('_', ' ')}")
        if p.get("special_needs"):
            lines.append(f"Special needs: {p['special_needs']}")
        if p.get("excitement"):
            lines.append(f"What engages them: {p['excitement']}")
        if p.get("teacher_insight"):
            lines.append(f"Teacher insight: {p['teacher_insight']}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)
