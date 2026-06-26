"""
Krishna Oracle — Frontier Model Pedagogical Advisor
====================================================

Architecture:
  Parth (Ollama/local)  = frontline tutor. Every message. Free, fast, private.
  Krishna (Claude/GPT4) = background advisor. Every N interactions. Reads the
                          child's full trajectory and writes strategic guidance
                          that Parth applies in subsequent sessions.

Krishna is called ASYNCHRONOUSLY — never in the critical request path.
If ANTHROPIC_API_KEY is absent, Krishna is silently disabled.

Trigger conditions:
  - Every KRISHNA_INTERVAL (default 10) interactions
  - When a misconception recurs ≥ 3 times on the same concept
  - (Future) Weekly digest for parent report enrichment

Output stored in foundation.krishna_guidance and pulled into Parth's
system prompt via build_learner_context().
"""
from __future__ import annotations

import json
import logging

import httpx

from config import Config
from foundation.observability import get_logger

log = get_logger("krishna.oracle")

_KRISHNA_SYSTEM = """You are Krishna — a master pedagogical advisor specialising in
Indian K-12 education. You receive a portrait of a child's learning journey and
write concise, evidence-based guidance for their AI tutor (Parth).

Your guidance must be:
- Specific and actionable (Parth can act on it immediately)
- Grounded in the child's actual behaviour patterns, not generic advice
- Culturally attuned to Indian educational context
- Written as instructions TO the tutor, not to the child

Return a JSON object with exactly these keys:
{
  "focus_concept": "<one concept Parth should prioritise next>",
  "analogy_suggestion": "<a concrete analogy or real-world hook for this child>",
  "teaching_strategy": "<2–3 sentence strategic direction for the next few sessions>",
  "encouragement_template": "<one sentence Parth can use verbatim to encourage this child>",
  "watch_out": "<one thing Parth should avoid with this child>"
}"""


async def consult(conn, learner_id: str, trigger: str = "periodic") -> dict | None:
    """
    Call the frontier model for pedagogical guidance on this learner.
    Stores result in foundation.krishna_guidance.
    Returns the guidance dict, or None if Krishna is disabled / API fails.
    """
    if not Config.ANTHROPIC_API_KEY:
        log.debug("krishna_disabled", reason="no ANTHROPIC_API_KEY")
        return None

    try:
        portrait = await _build_portrait(conn, learner_id)
        guidance = await _call_anthropic(portrait)
        if guidance:
            await _store(conn, learner_id, trigger, guidance)
            log.info("krishna_guidance_stored",
                     learner_id=learner_id, trigger=trigger,
                     focus=guidance.get("focus_concept", ""))
        return guidance
    except Exception as e:
        log.warning("krishna_consult_failed", learner_id=learner_id, error=str(e))
        return None


async def get_latest_guidance(conn, learner_id: str) -> dict | None:
    """Return the most recent unapplied Krishna guidance for this learner."""
    row = await conn.fetchrow(
        """
        SELECT guidance FROM foundation.krishna_guidance
        WHERE learner_id = $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        learner_id,
    )
    return dict(row["guidance"]) if row else None


async def mark_applied(conn, learner_id: str):
    """Mark the latest guidance row as applied (applied in this session's prompt)."""
    await conn.execute(
        """
        UPDATE foundation.krishna_guidance SET applied = true
        WHERE learner_id = $1
          AND id = (
              SELECT id FROM foundation.krishna_guidance
              WHERE learner_id = $1
              ORDER BY created_at DESC LIMIT 1
          )
        """,
        learner_id,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _build_portrait(conn, learner_id: str) -> str:
    """Assemble a concise learning portrait from DB data."""
    from modules.learner_state.psyche import compute_mbti, interpret_psyche

    profile = await conn.fetchrow(
        "SELECT name, grade, streak_days, engagement_score, last_emotion, "
        "       language_ratio, total_questions "
        "FROM learner_state.profiles WHERE learner_id = $1",
        learner_id,
    )
    if not profile:
        return f"Learner {learner_id} — no profile yet."

    psyche_row = await conn.fetchrow(
        "SELECT * FROM learner_state.psyche WHERE learner_id = $1", learner_id
    )
    psyche = dict(psyche_row) if psyche_row else {}

    recent = await conn.fetch(
        """
        SELECT subject, emotion, engagement, misconception, question
        FROM learner_state.interactions
        WHERE learner_id = $1
        ORDER BY created_at DESC LIMIT 15
        """,
        learner_id,
    )

    weak = await conn.fetch(
        """
        SELECT concept_id, p_mastery, misconceptions
        FROM learner_state.knowledge
        WHERE learner_id = $1 AND p_mastery < 0.5
        ORDER BY p_mastery ASC LIMIT 5
        """,
        learner_id,
    )

    misconceptions = await conn.fetch(
        """
        SELECT concept_id, misconception, count
        FROM learner_state.misconception_map
        WHERE learner_id = $1
        ORDER BY count DESC, last_seen DESC LIMIT 5
        """,
        learner_id,
    )

    lang = "English" if profile["language_ratio"] > 0.8 else (
           "Hindi" if profile["language_ratio"] < 0.3 else "Hindi-English mix")

    mbti = compute_mbti(psyche) if psyche else {}
    mbti_line = (f"Personality type: {mbti['type']} {mbti['name']} ({mbti['confidence']} confidence)"
                 if mbti.get("type") else "Personality: insufficient data")

    lines = [
        f"LEARNER PORTRAIT — {profile['name'] or learner_id}, Grade {profile['grade']}",
        f"Total questions: {profile['total_questions']} | Streak: {profile['streak_days']} days",
        f"Language: {lang} | Current emotion: {profile['last_emotion']} "
        f"| Engagement: {profile['engagement_score']:.1f}/10",
        mbti_line,
        "",
        "RECENT INTERACTIONS (last 15):",
    ]

    for r in recent:
        misc = f" [MISCONCEPTION: {r['misconception'][:60]}]" if r["misconception"] else ""
        lines.append(
            f"  [{r['subject']}] emotion={r['emotion']} eng={r['engagement']:.0f} "
            f"Q: {(r['question'] or '')[:80]}{misc}"
        )

    if weak:
        lines.append("\nWEAK CONCEPTS:")
        for w in weak:
            lines.append(f"  {w['concept_id']} mastery={w['p_mastery']:.2f} "
                         f"misconceptions={w['misconceptions']}")

    if misconceptions:
        lines.append("\nPERSISTENT MISCONCEPTIONS:")
        for m in misconceptions:
            lines.append(f"  [{m['count']}x] {m['concept_id']}: {m['misconception'][:80]}")

    if psyche:
        lines.append(f"\nPSYCHE PROFILE (sample_count={psyche.get('sample_count',0)}):")
        for dim in ["conscientiousness", "growth_mindset", "anxiety",
                    "depth_preference", "mastery_orientation", "extroversion", "thinking_feeling"]:
            lines.append(f"  {dim}: {psyche.get(dim, 0.5):.2f}")

    return "\n".join(lines)


async def _call_anthropic(portrait: str) -> dict | None:
    prompt = (
        "Here is the learner portrait:\n\n"
        + portrait
        + "\n\nWrite your guidance JSON now."
    )
    payload = {
        "model": Config.KRISHNA_MODEL,
        "max_tokens": 512,
        "system": _KRISHNA_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=30) as client:
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
        text = r.json()["content"][0]["text"].strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)


async def _store(conn, learner_id: str, trigger: str, guidance: dict):
    from modules.learner_state.psyche import compute_mbti, get_psyche
    psyche = await get_psyche(conn, learner_id)
    mbti = compute_mbti(psyche)
    await conn.execute(
        """
        INSERT INTO foundation.krishna_guidance
            (learner_id, trigger, mbti_type, guidance)
        VALUES ($1, $2, $3, $4)
        """,
        learner_id,
        trigger,
        mbti.get("type"),
        json.dumps(guidance),
    )
