"""
observation.engine — turn one real-world thing a student noticed into
several genuinely cross-domain Socratic openings.

Not a new subsystem: this module's only real job is producing the JSON
below. Storage reuses learner_state/episodes.py and open_loops.py
unchanged (see main.py's /observation endpoint), so every existing,
already-live adaptation mechanism (emotion, register, curriculum
context) applies to the resulting conversation automatically, from the
next /chat turn onward.

Precondition: an observation_text and a grade. Effect: no DB write
happens in this module — generate_cross_domain_probes() is a pure
Function (LLM call in, structured data out); the caller (main.py) is
responsible for storing it as an Action, per CONVENTIONS.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from config import Config
from foundation.observability import get_logger
from modules.learner_state import episodes, open_loops

log = get_logger("observation.engine")

MAX_PROBES = 5
MIN_PROBES = 3


@dataclass
class Probe:
    domain: str                # e.g. "biology", "physics", "philosophy/ethics"
    opening_question: str      # ONE Socratic question — never an explanation
    why_this_angle: str        # short internal rationale, for logging/portrait use
    concept_ids: list[str] = field(default_factory=list)  # best-effort curriculum grounding


@dataclass
class ObservationResult:
    probes: list[Probe]
    opening_message: str       # probes[0], phrased in Parth's actual voice


_PROMPT_TEMPLATE = """\
A student told you something they noticed in real life. Your job is NOT \
to explain it to them. Your job is to find {n_probes} genuinely different \
academic angles hiding inside this one moment, and for each one, write \
ONE Socratic question that would make the student want to think it \
through themselves — never a lecture, never an answer.

What the student noticed:
"{observation_text}"

Student's grade level: {grade} ({register_hint}).

Rules:
- Each angle must be a DIFFERENT subject/discipline. Good angles for a \
real-world observation usually include some mix of: biology (behavior, \
instinct, physiology), physics (forces, motion, energy), chemistry \
(what's happening at a molecular/reaction level), philosophy or ethics \
(a genuine dilemma or question of value/knowledge hiding in the \
situation), and economics/game theory/logic (competition, incentives, \
inference from incomplete evidence). Only include an angle if it is \
GENUINELY grounded in the specific details the student described — do \
not force a domain that doesn't fit. It is better to return 3 strong, \
specific angles than 5 where the last one or two are a stretch.
- The opening_question must be answerable by thinking about THIS specific \
observation, not a generic textbook question. It should feel like a \
question only someone who actually heard this exact story would ask.
- Do not explain the concept in the question. Ask, don't tell.
- Keep each opening_question to one sentence. Keep why_this_angle to 6-10 \
words — a tag, not an explanation.
{concept_hint}
Respond with ONLY valid, COMPLETE JSON (every object and array closed, no \
trailing commas), no other text, in this exact shape:
{{"probes":[{{"domain":"...","opening_question":"...","why_this_angle":"..."}}],"opening_message":"..."}}

"probes" must have between {min_probes} and {n_probes} entries, ordered \
strongest-fit-for-this-student first. "opening_message" is probes[0]'s \
question, rewritten as Parth (a warm, curious mentor) would actually say \
it out loud to this student — natural spoken register, not a textbook \
sentence, {tone_note}."""


def _register_hint(grade: int) -> str:
    if grade >= 11:
        return "preparing for IIT/NEET-style entrance exams — treat them as capable of real depth"
    if grade >= 9:
        return "upper secondary"
    return "middle school"


def _tone_note(grade: int) -> str:
    if grade >= 11:
        return "serious and respectful, no baby talk, no exclamation-mark enthusiasm"
    return "warm and encouraging"


def _concept_hint(candidates: list[dict]) -> str:
    if not candidates:
        return ""
    listed = "; ".join(f"{c['id']}: {c['label']}" for c in candidates[:12])
    return (
        f"\nIf any of these curriculum concepts genuinely apply to a probe, "
        f"include its id in that probe's concept_ids (only if it truly fits — "
        f"leave concept_ids empty rather than force a match): {listed}\n"
    )


def _build_prompt(observation_text: str, grade: int, candidates: list[dict]) -> str:
    return _PROMPT_TEMPLATE.format(
        n_probes=MAX_PROBES,
        min_probes=MIN_PROBES,
        observation_text=observation_text.strip()[:1000],
        grade=grade,
        register_hint=_register_hint(grade),
        concept_hint=_concept_hint(candidates),
        tone_note=_tone_note(grade),
    )


async def _candidate_concepts(conn, grade: int) -> list[dict]:
    """Best-effort curriculum grounding — not a hard dependency. Grade
    11-12 has no seeded concepts today (confirmed against curriculum_seed.sql),
    so this legitimately returns an empty list for that band, and the
    prompt is written to treat concept_ids as optional, not a required
    match."""
    rows = await conn.fetch(
        """
        SELECT id, label FROM curriculum_graph.concepts
        WHERE grade_min <= $1 AND grade_max >= $1
        ORDER BY label
        LIMIT 20
        """,
        grade,
    )
    return [dict(r) for r in rows]


def _extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group())


MAX_OUTPUT_TOKENS = 1536


async def _call_anthropic(prompt: str) -> str:
    payload = {
        "model": Config.TUTOR_MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.5,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": Config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()


async def _call_ollama(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{Config.OLLAMA_URL}/api/chat",
            json={
                "model": Config.FAST_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.5, "num_predict": MAX_OUTPUT_TOKENS, "num_ctx": 8192},
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


async def generate_cross_domain_probes(
    conn, observation_text: str, grade: int, learner_context: str = "",
) -> ObservationResult:
    """The one LLM call this module makes. Grounds against real curriculum
    concepts where they exist (best-effort — see _candidate_concepts) and
    returns 3-5 genuinely distinct, Socratic (question-first, not
    lecturing) cross-domain openings, ranked strongest-first."""
    candidates = await _candidate_concepts(conn, grade)
    prompt = _build_prompt(observation_text, grade, candidates)
    if learner_context:
        prompt += f"\n\nWhat you already know about this student:\n{learner_context}"

    use_anthropic = Config.use_anthropic_tutor()

    async def _one_attempt() -> dict:
        raw = await _call_anthropic(prompt) if use_anthropic else await _call_ollama(prompt)
        return _extract_json(raw)

    try:
        data = await _one_attempt()
    except Exception as e:
        # Retry once — mirrors tutor_runtime's verify_math retry-once
        # convention. A local model occasionally truncates or malforms
        # JSON on a long structured response; one retry is cheap and
        # usually succeeds where the first attempt didn't.
        log.warning("observation_generation_retry", error=str(e))
        try:
            data = await _one_attempt()
        except Exception as e2:
            log.error("observation_generation_failed", error=str(e2))
            raise

    probes = [
        Probe(
            domain=p.get("domain", "").strip(),
            opening_question=p.get("opening_question", "").strip(),
            why_this_angle=p.get("why_this_angle", "").strip(),
            concept_ids=[c for c in p.get("concept_ids", []) if isinstance(c, str)],
        )
        for p in data.get("probes", [])
        if p.get("opening_question")
    ]
    if len(probes) < MIN_PROBES:
        log.warning("observation_too_few_probes", count=len(probes))

    opening_message = data.get("opening_message", "").strip() or (
        probes[0].opening_question if probes else ""
    )
    return ObservationResult(probes=probes, opening_message=opening_message)


# ── Storage — the Action half; generate_cross_domain_probes above is the ────
#    pure Function half. Precondition: result.probes may be empty (a failed
#    or thin generation) — this still stores the raw observation as one
#    episode so it isn't silently lost, but skips the open_loop plant if
#    there's no real question to plant. Effect: one episode per probe (all
#    tagged episode_type="observation"), plus one open_loop for the
#    strongest (first-ranked) probe. Idempotent is not meaningful here —
#    each call is a new, distinct observation, not a repeat of a prior one.
async def store_observation(
    conn, learner_id: str, observation_text: str, result: ObservationResult,
) -> None:
    if not result.probes:
        await episodes.store(
            conn, learner_id, "observation", observation_text,
            concepts=[], patterns=[],
        )
        log.warning("observation_stored_with_no_probes", learner_id=learner_id)
        return

    for probe in result.probes:
        ep = await episodes.store(
            conn, learner_id, "observation", observation_text,
            concepts=probe.concept_ids, patterns=[],
        )
        # episodes.store() computes its own generic follow_up; overwrite it
        # with this probe's actual Socratic question, which is the whole
        # point of an observation-sourced episode.
        await conn.execute(
            "UPDATE learner_state.episodes SET follow_up = $1 WHERE id = $2",
            probe.opening_question, ep["id"],
        )

    strongest = result.probes[0]
    await open_loops.store(
        conn, learner_id, strongest.opening_question, strongest.concept_ids,
    )
    log.info("observation_stored", learner_id=learner_id, probe_count=len(result.probes))
