"""
Teacher feedback API — receives portrait form submissions and serves the form HTML.

Flow:
  1. Teacher receives WhatsApp link: /teacher/form?code=A1B2C3D4
  2. They fill the form, which POSTs JSON to /teacher/feedback
  3. We resolve student_code → learner_id (first 8 chars of UUID, case-insensitive)
  4. Store in teacher.portraits; upsert on (student_code, subject) so resubmission updates
  5. /chat injects the portrait into learner_context via get_teacher_portrait_context()
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from foundation.db import get_pool
from foundation.observability import get_logger

log = get_logger("teacher.routes")

router = APIRouter(prefix="/teacher", tags=["teacher"])


# ── Pydantic model (all fields optional except the three required ones) ───────

class TeacherFeedbackRequest(BaseModel):
    student_code:       str
    teacher_name:       str
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/form")
async def teacher_form():
    return FileResponse("static/teacher_form.html")


@router.post("/feedback")
async def submit_feedback(body: TeacherFeedbackRequest):
    code = body.student_code.upper().strip()
    if len(code) < 4:
        raise HTTPException(status_code=422, detail="student_code too short")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Resolve student_code → full learner_id
        # The join code is the first 8 chars of the UUID (no dashes in the first segment)
        learner_row = await conn.fetchrow(
            "SELECT learner_id FROM learner_state.profiles WHERE UPPER(SUBSTR(learner_id, 1, 8)) = $1",
            code,
        )
        learner_id = learner_row["learner_id"] if learner_row else None

        if not learner_id:
            log.warning("teacher_portrait_unresolved_code", code=code)

        payload = body.model_dump(exclude={"student_code", "teacher_name", "subject"})

        await conn.execute(
            """
            INSERT INTO teacher.portraits
                (student_code, learner_id, teacher_name, subject, payload, submitted_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, now())
            ON CONFLICT (student_code, subject) DO UPDATE
                SET learner_id   = COALESCE($2, teacher.portraits.learner_id),
                    teacher_name = $3,
                    payload      = $5::jsonb,
                    submitted_at = now()
            """,
            code, learner_id, body.teacher_name, body.subject,
            json.dumps(payload),
        )

        log.info("teacher_portrait_saved", code=code, learner_id=learner_id,
                 subject=body.subject)

    return {"status": "ok", "learner_id": learner_id}


# ── Portrait context builder — called by learner_state module ────────────────

async def get_teacher_portrait_context(conn, learner_id: str) -> str:
    """
    Return a compact teacher portrait string to inject into the tutor's system prompt.
    Returns empty string if no portraits exist yet.
    """
    rows = await conn.fetch(
        """
        SELECT teacher_name, subject, payload
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
        lines = [f"Subject: {subj} (from {row['teacher_name']})"]

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
