"""Assembles the final system prompt from kernel context slices."""
from config import Config


def build_system_prompt(ctx) -> str:
    """ctx is a KernelContext with learner_context and curriculum_context filled in."""
    return Config.system_prompt(
        subject=ctx.subject,
        context=ctx.curriculum_context,
        learner_context=ctx.learner_context,
    )


def build_messages(ctx, system_prompt: str) -> list[dict]:
    messages = [
        {"role": "user", "content": system_prompt},
        {
            "role": "assistant",
            "content": "Namaste! I'm Parth, your personal AI mentor. Ask me anything!",
        },
    ]
    for m in ctx.history[-16:]:
        role = m.get("role", "user") if isinstance(m, dict) else m.role
        content = m.get("content", "") if isinstance(m, dict) else m.content
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": ctx.message})
    return messages
