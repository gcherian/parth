"""
BMAD Guardian Onboarding Agent.

A conversational agent that interviews a guardian across 12 questions,
interprets free-form answers via LLM, and produces a per-child agent
configuration written to child_agent_config + child_global_config.

This is "AI configuring AI":
  Guardian → BMAD onboarding agent → child_agent_config → 15 runtime agents

Flow:
  1. start()    — create session, return greeting + first question
  2. answer()   — LLM interprets answer → acknowledgment + next question
  3. apply()    — write derived_config to DB, mark onboarding complete

Session state lives in-memory (_sessions dict) and is periodically
flushed to learner_state.onboarding for persistence / restart recovery.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from config import Config
from foundation.observability import get_logger
from modules.learner_state.child_config import (
    AGENT_SCHEMA, GLOBAL_SCHEMA, ONBOARDING_QUESTIONS,
)

log = get_logger("bmad.onboarding")

# ── In-memory session store ───────────────────────────────────────────────────
_sessions: dict[str, "OnboardingSession"] = {}


@dataclass
class OnboardingSession:
    session_id:    str
    learner_id:    str
    learner_name:  str
    guardian_name: str
    current_q_idx: int               = 0        # index into ONBOARDING_QUESTIONS
    responses:     dict              = field(default_factory=dict)   # {q_id: raw text}
    understood:    dict              = field(default_factory=dict)   # {q_id: confirmation sentence}
    derived_config: dict             = field(default_factory=dict)   # {agent: {key: val}}
    global_config:  dict             = field(default_factory=dict)   # exam_prep_mode, etc.
    status:        str               = "in_progress"
    started_at:    str               = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── LLM interpretation ────────────────────────────────────────────────────────

def _build_interpretation_prompt(
    q: dict, answer: str, child_name: str
) -> list[dict]:
    """
    Build messages for the LLM to interpret one guardian answer.
    Returns structured JSON with config values + a warm confirmation sentence.
    """
    informs = q.get("informs", [])

    # Build constraint description for each informed key
    constraints = []
    for agent_name, key in informs:
        if agent_name == "_global":
            spec = GLOBAL_SCHEMA.get(key, {})
        else:
            spec = AGENT_SCHEMA.get(agent_name, {}).get(key, {})
        if not spec:
            continue
        t = spec.get("type", "str")
        if t == "enum":
            constraints.append(f'  - {agent_name}.{key}: one of {spec["values"]} (default: {spec["default"]!r})')
        elif t == "bool":
            constraints.append(f'  - {agent_name}.{key}: true or false (default: {spec["default"]!r})')
        elif t == "int":
            constraints.append(f'  - {agent_name}.{key}: integer {spec.get("min","?")}–{spec.get("max","?")} (default: {spec["default"]!r})')
        elif t == "float":
            constraints.append(f'  - {agent_name}.{key}: float {spec.get("min","?")}–{spec.get("max","?")} (default: {spec["default"]!r})')
        elif t == "list":
            constraints.append(f'  - {agent_name}.{key}: list from {spec.get("values", ["any"])} (default: {spec["default"]!r})')
        elif t == "date":
            constraints.append(f'  - {agent_name}.{key}: ISO date YYYY-MM-DD or null (default: null)')
        else:
            constraints.append(f'  - {agent_name}.{key}: string (default: {spec["default"]!r})')

    constraint_str = "\n".join(constraints) if constraints else "  (no config keys — just collect the answer)"

    system = (
        "You are a BMAD configuration agent for Parth, an AI tutor for Indian children. "
        "A guardian has answered an onboarding question. Your job is to:\n"
        "1. Interpret their free-form answer into exact config values\n"
        "2. Write a single warm, specific confirmation sentence (in English) telling the guardian "
        "   what Parth now understands about their child — cite the actual value chosen\n\n"
        "Return ONLY valid JSON. No markdown, no explanation outside the JSON.\n"
        "Format:\n"
        '{\n'
        '  "understood": "Parth will... (one sentence, warm, specific to the answer)",\n'
        '  "config": [\n'
        '    {"agent": "agent_name_or__global", "key": "config_key", "value": <typed_value>}\n'
        '  ]\n'
        '}'
    )

    user = (
        f"Child's name: {child_name}\n\n"
        f"Onboarding question asked:\n\"{q['text']}\"\n\n"
        f"Guardian's answer:\n\"{answer}\"\n\n"
        f"Config keys this question informs:\n{constraint_str}\n\n"
        "Return the JSON now."
    )

    return [
        {"role": "user",      "content": system},
        {"role": "assistant", "content": "I will interpret the guardian's answer and return only valid JSON:"},
        {"role": "user",      "content": user},
    ]


async def _interpret(q: dict, answer: str, child_name: str) -> tuple[str, list[dict]]:
    """
    Call LLM to interpret one guardian answer.
    Returns (understood_sentence, [{agent, key, value}, ...])
    """
    if not q.get("informs"):
        # No config mapping — just acknowledge
        return f"Got it — Parth has noted {child_name}'s subject strengths and will adjust accordingly.", []

    messages = _build_interpretation_prompt(q, answer, child_name)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model":   Config.FAST_MODEL,
                    "messages": messages,
                    "stream":  False,
                    "options": {"temperature": 0.1},   # low temp — we want deterministic config
                },
            )
            r.raise_for_status()
            raw = r.json()["message"]["content"].strip()

            # Strip markdown code fences if model adds them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            parsed = json.loads(raw)
            understood = parsed.get("understood", "Understood.")
            config_items = parsed.get("config", [])
            return understood, config_items

    except Exception as exc:
        log.warning("interpretation_failed", question=q["id"], error=str(exc))
        # Graceful fallback — use defaults, confirm receipt
        return f"Got it — I've noted that for {child_name}.", []


# ── Session management ────────────────────────────────────────────────────────

def _question_text(idx: int, child_name: str) -> str:
    q = ONBOARDING_QUESTIONS[idx]
    # Personalise the question with the child's name on first use
    return q["text"]


def start(learner_id: str, learner_name: str, guardian_name: str) -> dict:
    """
    Create a new onboarding session. Returns the greeting message and first question.
    """
    session_id = str(uuid.uuid4())
    session = OnboardingSession(
        session_id=session_id,
        learner_id=learner_id,
        learner_name=learner_name,
        guardian_name=guardian_name,
    )
    _sessions[session_id] = session

    first_q = ONBOARDING_QUESTIONS[0]
    greeting = (
        f"Namaste {guardian_name}! I'm Parth's onboarding assistant. "
        f"Before {learner_name} meets Parth, I'd like to understand them better. "
        f"This takes about 3 minutes — 12 quick questions. "
        f"There are no right or wrong answers; the more detail you share, the better Parth can personalise the experience.\n\n"
        f"Let's begin."
    )

    return {
        "session_id":    session_id,
        "message":       greeting,
        "question":      first_q["text"],
        "question_id":   first_q["id"],
        "question_num":  1,
        "total":         len(ONBOARDING_QUESTIONS),
        "status":        "in_progress",
    }


async def answer(session_id: str, text: str) -> dict:
    """
    Process one guardian answer. Interprets it, advances to next question.
    Returns the acknowledgment + next question (or completion summary).
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": "Session not found. Please start a new onboarding session."}

    if session.status == "complete":
        return {"error": "Onboarding already complete.", "status": "complete"}

    q   = ONBOARDING_QUESTIONS[session.current_q_idx]
    qid = q["id"]

    # Store raw answer
    session.responses[qid] = text

    # Interpret answer via LLM
    understood, config_items = await _interpret(q, text, session.learner_name)
    session.understood[qid] = understood

    # Merge config items into session state
    for item in config_items:
        agent = item.get("agent", "")
        key   = item.get("key", "")
        value = item.get("value")
        if agent == "_global":
            session.global_config[key] = value
        elif agent and key:
            session.derived_config.setdefault(agent, {})[key] = value

    # Advance
    session.current_q_idx += 1
    complete = session.current_q_idx >= len(ONBOARDING_QUESTIONS)

    if complete:
        session.status = "complete"
        return {
            "session_id":   session_id,
            "understood":   understood,
            "status":       "complete",
            "summary":      _build_summary(session),
            "config":       session.derived_config,
            "global_config": session.global_config,
        }

    next_q   = ONBOARDING_QUESTIONS[session.current_q_idx]
    return {
        "session_id":    session_id,
        "understood":    understood,
        "question":      next_q["text"],
        "question_id":   next_q["id"],
        "question_num":  session.current_q_idx + 1,
        "total":         len(ONBOARDING_QUESTIONS),
        "status":        "in_progress",
    }


def _build_summary(session: OnboardingSession) -> list[dict]:
    """Human-readable summary of what was configured — shown to guardian at end."""
    lines = []
    for qid, text in session.understood.items():
        lines.append({"question_id": qid, "understood": text})
    return lines


def get_session(session_id: str) -> Optional[dict]:
    s = _sessions.get(session_id)
    if not s:
        return None
    return {
        "session_id":    s.session_id,
        "learner_id":    s.learner_id,
        "learner_name":  s.learner_name,
        "guardian_name": s.guardian_name,
        "current_q_idx": s.current_q_idx,
        "status":        s.status,
        "responses":     s.responses,
        "understood":    s.understood,
        "derived_config": s.derived_config,
        "global_config": s.global_config,
    }


# ── DB persistence ────────────────────────────────────────────────────────────

async def apply(session_id: str, conn) -> dict:
    """
    Write the derived config to child_agent_config and child_global_config.
    Marks onboarding as complete in learner_state.onboarding.
    Returns summary of what was written.
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": "Session not found."}
    if session.status != "complete":
        return {"error": "Onboarding not yet complete. Answer all questions first."}

    written_agents = []

    # Write per-agent config
    for agent_name, config in session.derived_config.items():
        if not config:
            continue
        await conn.execute(
            """INSERT INTO learner_state.child_agent_config
               (learner_id, agent_name, config, set_by, notes, created_at, updated_at)
               VALUES ($1, $2, $3, 'bmad_onboarding', 'Set during guardian onboarding', now(), now())
               ON CONFLICT (learner_id, agent_name) DO UPDATE
               SET config = $3, set_by = 'bmad_onboarding', updated_at = now()""",
            session.learner_id,
            agent_name,
            json.dumps(config),
        )
        written_agents.append(agent_name)

    # Write global config
    gc = session.global_config
    if gc:
        await conn.execute(
            """INSERT INTO learner_state.child_global_config
               (learner_id, exam_prep_mode, exam_date, max_response_words, session_persona, set_by, updated_at)
               VALUES ($1,
                       $2::boolean,
                       $3::date,
                       $4,
                       $5,
                       'bmad_onboarding',
                       now())
               ON CONFLICT (learner_id) DO UPDATE
               SET exam_prep_mode    = $2::boolean,
                   exam_date         = $3::date,
                   max_response_words = $4,
                   session_persona    = $5,
                   set_by             = 'bmad_onboarding',
                   updated_at         = now()""",
            session.learner_id,
            bool(gc.get("exam_prep_mode", False)),
            gc.get("exam_date"),
            int(gc.get("max_response_words", 200)),
            gc.get("session_persona", "auto"),
        )

    # Persist onboarding record
    await conn.execute(
        """INSERT INTO learner_state.onboarding
           (learner_id, status, responses, derived_config, completed_at, created_at, updated_at)
           VALUES ($1, 'complete', $2, $3, now(), now(), now())
           ON CONFLICT (learner_id) DO UPDATE
           SET status = 'complete', responses = $2, derived_config = $3,
               completed_at = now(), updated_at = now()""",
        session.learner_id,
        json.dumps(session.responses),
        json.dumps({**session.derived_config, "_global": session.global_config}),
    )

    log.info("onboarding_applied",
             learner_id=session.learner_id,
             agents_configured=written_agents,
             global_keys=list(gc.keys()))

    # Clean up memory
    del _sessions[session_id]

    return {
        "learner_id":         session.learner_id,
        "agents_configured":  written_agents,
        "global_config_keys": list(gc.keys()),
        "summary":            _build_summary(session),
        "status":             "applied",
    }
