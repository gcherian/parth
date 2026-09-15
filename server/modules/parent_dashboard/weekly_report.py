"""
Parent weekly report — plain-English, teacher-attributed (business plan §7.3).

Business plan quote: "Weekly, plain English, specific, issued by the tuition
class. ... No tuition teacher in India currently sends a parent that
sentence, and no parent who receives it forgets who sent it."

Distinct from modules.lens.contextual's narrative: that one is framed as a
third-party "learning analytics specialist" writing a portrait for a teacher
or guardian. This module writes AS the named teacher, TO the parent, and
grounds every sentence in facts already computed by
modules.parent_dashboard.module.gather_report_facts — no numbers or claims
are invented by the LLM.

Not wired to a scheduler. generate_and_send() is the callable a future cron
job (or admin action) would call once a week per (learner, teacher) pair —
see server/CONVENTIONS.md and the PR description for what's deliberately
left out.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from config import Config
from foundation.identity import check_consent, SCOPE_PROGRESS_REPORT
from foundation.observability import get_logger
from modules.parent_dashboard.module import gather_report_facts

log = get_logger("parent.weekly_report")


def _week_start(today: Optional[date] = None) -> date:
    """Monday of the current ISO week — the key a re-run for the same week updates."""
    d = today or datetime.now(timezone.utc).date()
    return d - timedelta(days=d.weekday())


def _fact_lines(facts: dict) -> dict:
    """
    Pull the handful of concrete, citable facts out of the parent_dashboard
    report payload that a weekly narrative should be grounded in. Returns
    plain strings, not raw rows, so the LLM prompt (and the no-LLM fallback)
    can drop them straight into a sentence.
    """
    weak = facts.get("weak_concepts") or []
    strong = facts.get("strong_concepts") or []
    recent_misconceptions = (facts.get("learning_ledger") or {}).get("recent_misconceptions") or []
    recall_due = (facts.get("school_readiness") or {}).get("recall_due") or []

    return {
        "subjects_covered": ", ".join(facts.get("subjects_covered") or []) or "general practice",
        "strong_concept": strong[0]["concept_id"] if strong else None,
        "weak_concept": weak[0]["concept_id"] if weak else None,
        "misconception": recent_misconceptions[0]["misconception"] if recent_misconceptions else None,
        "recall_due_concept": recall_due[0]["concept_id"] if recall_due else None,
        "streak_days": facts.get("streak_days") or 0,
    }


async def _generate_narrative(teacher_name: str, student_name: str, facts: dict) -> str:
    """
    Draft the weekly report in the teacher's own voice, grounded in `facts`
    (from gather_report_facts). Falls back to a template sentence — built
    from the same facts, not invented — if the LLM call fails.
    """
    f = _fact_lines(facts)

    system_msg = (
        f"You are {teacher_name}, this student's tuition teacher, writing "
        "directly to the parent — not a third-party analyst, not the app. "
        "Plain English, warm but specific, 60-100 words, continuous prose, "
        "no bullet points, no third-person references to 'the teacher' or "
        "'the analytics'. Sign off as yourself. Only state facts given below "
        "— do not invent numbers, subjects, or topics not listed."
    )
    user_msg = f"""Write this week's report for {student_name}'s parent.

Facts to ground it in (use only these — do not add others):
- Subjects covered this week: {f['subjects_covered']}
- Concept understood well: {f['strong_concept'] or 'none yet flagged as strong'}
- Concept still shaky: {f['weak_concept'] or 'none currently flagged as weak'}
- A specific misconception observed: {f['misconception'] or 'none recorded this week'}
- A topic due for recall practice: {f['recall_due_concept'] or 'none due'}
- Current streak: {f['streak_days']} days

Write the report now, signed as {teacher_name}."""

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.FAST_MODEL,
                    "messages": [
                        {"role": "user", "content": system_msg},
                        {"role": "assistant", "content": "Understood. Here is the report:"},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.4},
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
    except Exception as exc:
        log.warning("weekly_report_llm_failed", error=str(exc))
        sentences = [f"This week {student_name} worked on {f['subjects_covered']}."]
        if f["strong_concept"]:
            sentences.append(f"{student_name} has understood {f['strong_concept']} and can apply it.")
        if f["misconception"]:
            sentences.append(f"{student_name} still believes {f['misconception']}, and we are working on it.")
        elif f["weak_concept"]:
            sentences.append(f"{f['weak_concept']} is still shaky, and we are working on it.")
        if f["recall_due_concept"]:
            sentences.append(f"Next, we'll revisit {f['recall_due_concept']} to keep it solid.")
        sentences.append(f"— {teacher_name}")
        return " ".join(sentences)


async def generate_and_send(
    pool,
    learner_id: str,
    teacher_name: str,
    teacher_phone: str,
    parent_contact: str,
    channel: str = "email",
) -> dict:
    """
    Precondition: learner_id names an already-registered child identity with
    active guardian consent covering SCOPE_PROGRESS_REPORT (checked here,
    before any read or write) — call foundation.identity.grant_pilot_consent
    (or the real OTP consent flow) first if this raises.

    Effect: reads this week's structured facts (mastery, misconceptions,
    recall-due) via parent_dashboard.gather_report_facts, drafts one
    plain-English narrative attributed to teacher_name, upserts it into
    parent_dashboard.weekly_reports for (learner_id, teacher_phone,
    this_week), and hands it to notify's 'parent_weekly_report' template
    for delivery to parent_contact over `channel`.

    Postcondition: exactly one row exists in parent_dashboard.weekly_reports
    for (learner_id, teacher_phone, week_start=this Monday) — safe to call
    again this week (ON CONFLICT DO UPDATE refreshes the narrative and
    notified flag rather than duplicating the row). Returns
    {"week_start", "narrative", "facts", "notify": <send_via_template result>}.

    Not wired to a scheduler — this is the function a future weekly cron
    (or an admin/teacher-triggered button) would call once per (learner,
    teacher) pair. No such scheduler exists yet; see PR description.
    """
    if not await check_consent(learner_id, SCOPE_PROGRESS_REPORT):
        raise PermissionError(
            f"no active guardian consent for scope '{SCOPE_PROGRESS_REPORT}' "
            f"on learner_id={learner_id}"
        )

    async with pool.acquire() as conn:
        facts = await gather_report_facts(conn, learner_id)
    # conn released before the LLM call, same lifecycle discipline as
    # lens/contextual.compute_and_save.

    student_name = facts.get("learner_name") or "your child"
    f = _fact_lines(facts)
    narrative = await _generate_narrative(teacher_name, student_name, facts)
    # Two claims this report makes are load-bearing and must hold every
    # time, not just on a lucky sampling of the LLM (temperature > 0):
    # specificity ("names the actual misconception, not a bare score") and
    # attribution ("no parent who receives it forgets who sent it"). Rather
    # than trust the prompt to include them verbatim, check and append.
    if f["misconception"] and f["misconception"].lower() not in narrative.lower():
        narrative = f"{narrative} Specifically, {student_name} currently believes {f['misconception']}."
    if teacher_name not in narrative and teacher_name.split()[-1] not in narrative:
        narrative = f"{narrative}\n\n— {teacher_name}"
    week_start = _week_start()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO parent_dashboard.weekly_reports
                (learner_id, teacher_phone, teacher_name, week_start, narrative, facts)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (learner_id, teacher_phone, week_start) DO UPDATE
                SET teacher_name = $3,
                    narrative    = $5,
                    facts        = $6,
                    notified     = false,
                    notified_at  = NULL,
                    updated_at   = now()
            """,
            learner_id, teacher_phone, teacher_name, week_start,
            narrative, json.dumps(facts, default=str),
        )

    from modules.notify.routes import send_via_template
    notify_result = await send_via_template(
        to=parent_contact,
        channel=channel,
        template="parent_weekly_report",
        params={
            "teacher_name": teacher_name,
            "student_name": student_name,
            "narrative": narrative,
        },
    )

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE parent_dashboard.weekly_reports
            SET notified = $4, notified_at = now()
            WHERE learner_id = $1 AND teacher_phone = $2 AND week_start = $3
            """,
            learner_id, teacher_phone, week_start,
            notify_result["status"] == "sent",
        )

    log.info(
        "parent_weekly_report_generated",
        learner_id=learner_id,
        teacher_phone=teacher_phone[-4:] if len(teacher_phone) > 4 else teacher_phone,
        week_start=str(week_start),
        notify_status=notify_result["status"],
    )

    return {
        "week_start": week_start.isoformat(),
        "teacher_name": teacher_name,
        "student_name": student_name,
        "narrative": narrative,
        "facts": facts,
        "notify": notify_result,
    }
