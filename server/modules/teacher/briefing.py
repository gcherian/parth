"""
Teacher "Tuesday briefing" — business plan §7.1.

Business-plan quote:
  "Before each batch, the teacher opens one screen: Six of your twenty-two
  are carrying the same misconception on equivalent fractions — named, with
  the specific wrong belief stated in one line. A four-minute opener that
  targets that belief... Three children who went quiet this week on a
  concept they had previously cleared. Two children ready to move ahead of
  the batch, with something to give them... it must be readable in ninety
  seconds on a phone... and it must never read as an instruction to him.
  Evidence, not verdict."

A teacher's "batch" is whatever set of learners are linked to them via
teacher.portraits (student_code resolved to learner_id at feedback-submission
time — see modules/teacher/routes.py). No new linking mechanism is added
here; this module only reads what's already there.

Read-only throughout — no learner_state row is created, changed, or removed,
so the CONVENTIONS.md mutation checklist (precondition/idempotent/consent
gate/etc.) doesn't apply to the query functions below. It does apply to the
demo's synthetic seed data, handled in tests/demo_gap_teacher_briefing.py.
"""
from datetime import datetime, timezone

from foundation.observability import get_logger
from modules.curriculum_graph.graph import get_remediation

log = get_logger("teacher.briefing")

# Same "mastered" bar learner_state/profile.py uses for analogy-domain
# retirement — reused here so "previously cleared" means the same thing
# everywhere in the codebase, not a second, competing definition of mastery.
_MASTERY_CLEARED_THRESHOLD = 0.72
# A higher bar than "cleared" — comfortably ahead, not just past the line,
# before we call a child out as ready to move beyond the batch.
_MASTERY_READY_THRESHOLD = 0.85
# "went quiet this week" — no profile activity in this many days.
_QUIET_DAYS = 6
# Caps straight from the business-plan quote itself ("Three children who
# went quiet", "Two children ready to move ahead") — not tunable knobs,
# they're what keeps the briefing at ninety-second, one-screen size.
_MAX_QUIET = 3
_MAX_READY = 2


def _label(concept_id: str, label_map: dict) -> str:
    return label_map.get(concept_id) or concept_id.replace("_", " ").title()


def _build_opener(remediation: dict | None) -> str:
    """Adapts the existing misconception-bank text rather than generating
    a fresh one — see curriculum_graph.get_remediation, whose output already
    is a short plain-language correction plus an optional memorable hook."""
    if not remediation:
        return ""
    parts = [remediation.get("remediation_text", "")]
    if remediation.get("analogy_hint"):
        parts.append(remediation["analogy_hint"])
    return " ".join(p for p in parts if p).strip()


async def _get_batch(conn, teacher_id: str) -> dict:
    """Returns {learner_id: student_name} for every learner this teacher_id
    (a teacher_phone) has linked via a teacher.portraits submission. Empty
    dict if the teacher hasn't linked anyone yet — a valid, if uninteresting,
    result, not an error."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (learner_id) learner_id, student_name
        FROM teacher.portraits
        WHERE teacher_phone = $1 AND learner_id IS NOT NULL
        ORDER BY learner_id, submitted_at DESC
        """,
        teacher_id,
    )
    return {r["learner_id"]: (r["student_name"] or "A student") for r in rows}


async def _find_shared_misconception(conn, learner_ids: list[str], names: dict, label_map: dict) -> dict | None:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (learner_id) learner_id, concept_id, misconception
        FROM learner_state.misconception_map
        WHERE learner_id = ANY($1::text[])
        ORDER BY learner_id, last_seen DESC
        """,
        learner_ids,
    )
    groups: dict[tuple, list[str]] = {}
    for r in rows:
        text = (r["misconception"] or "").strip()
        if not text:
            continue
        key = (r["concept_id"], text.lower())
        groups.setdefault(key, []).append(r["learner_id"])

    if not groups:
        return None

    (concept_id, _norm), holder_ids = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(holder_ids) < 2:
        return None  # not "shared" unless at least two children hold it

    original_text = next(
        r["misconception"] for r in rows
        if r["concept_id"] == concept_id and (r["misconception"] or "").strip().lower() == _norm
    )
    remediation = await get_remediation(conn, concept_id, original_text)

    return {
        "concept": _label(concept_id, label_map),
        "belief": original_text,
        "children": [names.get(lid, "A student") for lid in holder_ids],
        "count": len(holder_ids),
        "opener": _build_opener(remediation),
    }


def _find_quiet_children(knowledge_rows: list, last_seen_by_learner: dict, names: dict, label_map: dict) -> list[dict]:
    """A child "went quiet" when they'd previously cleared at least one
    concept (p_mastery >= _MASTERY_CLEARED_THRESHOLD) but their profile shows
    no activity in the last _QUIET_DAYS days. Compares against the concept
    they hold their highest mastery on, as required — "on a concept they had
    previously cleared", not just silence in the abstract."""
    now = datetime.now(timezone.utc)
    best_cleared: dict[str, tuple] = {}
    for r in knowledge_rows:
        if r["p_mastery"] is None or r["p_mastery"] < _MASTERY_CLEARED_THRESHOLD:
            continue
        prev = best_cleared.get(r["learner_id"])
        if prev is None or r["p_mastery"] > prev[1]:
            best_cleared[r["learner_id"]] = (r["concept_id"], r["p_mastery"])

    quiet = []
    for learner_id, (concept_id, _mastery) in best_cleared.items():
        last_seen = last_seen_by_learner.get(learner_id)
        if last_seen is None:
            continue
        days_quiet = (now - last_seen).days
        if days_quiet >= _QUIET_DAYS:
            quiet.append({
                "name": names.get(learner_id, "A student"),
                "concept": _label(concept_id, label_map),
                "quiet_for_days": days_quiet,
            })

    quiet.sort(key=lambda q: -q["quiet_for_days"])
    return quiet


async def _find_ready_to_advance(conn, knowledge_rows: list, names: dict, label_map: dict) -> list[dict]:
    """Finds the concept most of the batch is still working through — the
    one with the most children below the ready bar, among concepts where at
    least one child has already cleared that bar — then names the children
    who are ahead of that pack. "of the batch" is the point: this is a
    relative, not absolute, read."""
    by_concept: dict[str, list] = {}
    for r in knowledge_rows:
        by_concept.setdefault(r["concept_id"], []).append(r)

    current_concept = None
    best_developing = -1
    for concept_id, rows in by_concept.items():
        developing = sum(1 for r in rows if r["p_mastery"] < _MASTERY_READY_THRESHOLD)
        ready = sum(1 for r in rows if r["p_mastery"] >= _MASTERY_READY_THRESHOLD)
        if developing > 0 and ready > 0 and developing > best_developing:
            best_developing = developing
            current_concept = concept_id

    if current_concept is None:
        return []

    next_concept = await conn.fetchval(
        """
        SELECT to_id FROM curriculum_graph.concept_edges
        WHERE from_id = $1 AND type IN ('leads-to', 'prerequisite')
        ORDER BY (type = 'leads-to') DESC
        LIMIT 1
        """,
        current_concept,
    )
    next_label = _label(next_concept, label_map) if next_concept else None

    return [
        {
            "name": names.get(r["learner_id"], "A student"),
            "concept": _label(current_concept, label_map),
            "next": next_label or "a stretch problem beyond this topic",
        }
        for r in by_concept[current_concept]
        if r["p_mastery"] >= _MASTERY_READY_THRESHOLD
    ]


async def build_teacher_briefing(conn, teacher_id: str) -> dict:
    """
    Precondition: none. teacher_id is a teacher_phone as used by
    teacher.portraits; a teacher_id with no linked students returns an
    empty-batch shape, not an error.

    Reads learner_state.misconception_map / .knowledge / .profiles and
    curriculum_graph for every learner linked to this teacher, and returns
    the "Tuesday briefing": the one misconception the most children share
    (named, with the belief stated in one line, plus a ready-made opener
    adapted from the existing remediation bank), up to three children quiet
    this week on a concept they'd previously cleared, and up to two children
    ready to move ahead of the batch.

    Read-only — no row is created, changed, or removed. Idempotent by
    construction (a pure read). Every line is a named, descriptive
    observation; nothing is phrased as an instruction to the teacher.
    """
    names = await _get_batch(conn, teacher_id)
    learner_ids = list(names)

    log.info("teacher_briefing_built", teacher_id=teacher_id[-4:], batch_size=len(learner_ids))

    if not learner_ids:
        return {
            "teacher_id": teacher_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "batch_size": 0,
            "shared_misconception": None,
            "quiet_children": [],
            "ready_to_advance": [],
            "note": "No students linked yet — link one via a /teacher/feedback submission with a student_code.",
        }

    knowledge_rows = await conn.fetch(
        """
        SELECT learner_id, concept_id, p_mastery
        FROM learner_state.knowledge
        WHERE learner_id = ANY($1::text[])
        """,
        learner_ids,
    )
    profile_rows = await conn.fetch(
        """
        SELECT learner_id, last_seen
        FROM learner_state.profiles
        WHERE learner_id = ANY($1::text[])
        """,
        learner_ids,
    )
    last_seen_by_learner = {r["learner_id"]: r["last_seen"] for r in profile_rows}

    concept_ids = {r["concept_id"] for r in knowledge_rows}
    label_rows = await conn.fetch(
        "SELECT id, label FROM curriculum_graph.concepts WHERE id = ANY($1::text[])",
        list(concept_ids),
    ) if concept_ids else []
    label_map = {r["id"]: r["label"] for r in label_rows}

    shared_misconception = await _find_shared_misconception(conn, learner_ids, names, label_map)
    quiet_children = _find_quiet_children(knowledge_rows, last_seen_by_learner, names, label_map)
    ready_to_advance = await _find_ready_to_advance(conn, knowledge_rows, names, label_map)

    return {
        "teacher_id": teacher_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_size": len(learner_ids),
        "shared_misconception": shared_misconception,
        "quiet_children": quiet_children[:_MAX_QUIET],
        "ready_to_advance": ready_to_advance[:_MAX_READY],
    }
