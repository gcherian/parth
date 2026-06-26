"""
Shared-world group chat — Parth guides 1-5 learners at a natural location.

Solo: Parth as personal guide, uses learner's knowledge as lens.
Group: Parth bridges each learner's knowledge through the shared location.
       Addresses students by name; plants cross-learner connections;
       ends with a collaboration question.
"""
from __future__ import annotations
import httpx
from config import Config
from foundation.observability import get_logger

log = get_logger("shared_world.chat")


def _build_system_prompt(location: dict, learners: list[dict]) -> str:
    loc_block = (
        f"LOCATION: {location['name']} {location['emoji']}\n"
        f"{location['description']}\n\n"
        f"WONDER: {location['wonder_hook']}"
    )

    if len(learners) == 1:
        l = learners[0]
        ctx_line = l.get("context", "")
        return f"""You are Parth, guiding {l['name']} on a solo exploration.

{loc_block}

LEARNER: {l['name']} — Grade {l['grade']}, {l['subject']}
{ctx_line}

Use THIS LOCATION as the lens through which their subject comes alive.
Connect what they see here to what they already know.
Be warm, wonder-filled, specific to this place.
End with a single question that pulls them one level deeper into the location.
4-6 sentences unless a step-by-step is needed."""

    # Group prompt
    names = ", ".join(l["name"] for l in learners[:-1]) + " and " + learners[-1]["name"]
    learner_lines = "\n".join(
        f"  • {l['name']} (Grade {l['grade']}, {l['subject']}): {l.get('context', 'just arrived')}"
        for l in learners
    )
    return f"""You are Parth, facilitating a GROUP DISCOVERY SESSION.

{loc_block}

PRESENT ({len(learners)} learners):
{learner_lines}

GROUP RULES:
- Address learners by name when speaking to them specifically.
- Use THIS LOCATION as the common thread connecting their different subjects.
- Find bridges: one child's knowledge should illuminate something for another.
- Celebrate connections: "Rishi — you know about DNA, and Dev — you know calculus. Here, they meet."
- End with a GROUP CHALLENGE that requires collaboration to answer.

GROUP CHALLENGE: {location.get('group_bonus', 'Explore together — what do you each notice first?')}

Keep responses 5-8 sentences. Be warm, specific, awe-filled."""


def _build_history(raw_messages: list[dict]) -> list[dict]:
    """Convert stored messages to Ollama chat format."""
    result = []
    for m in raw_messages:
        role = "assistant" if m["role"] == "parth" else "user"
        prefix = f"{m['learner_name']}: " if m["role"] == "child" and m.get("learner_name") else ""
        result.append({"role": role, "content": prefix + m["content"]})
    return result


async def generate_response(
    location: dict,
    learners: list[dict],
    new_message: str,
    speaker_name: str,
    history: list[dict],
) -> str:
    """Call Ollama and return Parth's response."""
    system = _build_system_prompt(location, learners)
    messages = [{"role": "system", "content": system}]
    messages.extend(_build_history(history))
    # Label the new message with the speaker's name in group mode
    prefix = f"{speaker_name}: " if len(learners) > 1 else ""
    messages.append({"role": "user", "content": prefix + new_message})

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={
                    "model": Config.FAST_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.75},
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
    except Exception as e:
        log.error("world_chat_error", error=str(e))
        raise
