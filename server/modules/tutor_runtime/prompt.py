"""Assembles the final system prompt from kernel context slices."""
from config import Config


def build_system_prompt(ctx) -> str:
    """ctx is a KernelContext with learner, curriculum, and optional graph context."""
    context_parts = []
    if ctx.curriculum_context:
        context_parts.append(ctx.curriculum_context)
    meaning_context = ctx.module_data.get("meaning.graph", {}).get("meaning_context", "")
    if meaning_context:
        context_parts.append(meaning_context)
    return Config.system_prompt(
        subject=ctx.subject,
        context="\n\n".join(context_parts),
        learner_context=ctx.learner_context,
    )


def build_messages(ctx, system_prompt: str) -> list[dict]:
    """Ollama-format: system prompt embedded as the first user turn."""
    messages = [
        {"role": "user", "content": system_prompt},
        {
            "role": "assistant",
            "content": "Namaste! I'm Parth, your personal AI mentor. Ask me anything!",
        },
    ]
    for m in ctx.history[-Config.MAX_HISTORY_TURNS:]:
        role = m.get("role", "user") if isinstance(m, dict) else m.role
        content = m.get("content", "") if isinstance(m, dict) else m.content
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": ctx.message})
    return messages


def build_anthropic_messages(ctx) -> tuple[str, list[dict]]:
    """
    Anthropic-format: returns (system_prompt, messages).
    System is separate; messages are alternating user/assistant starting with user.
    """
    system_prompt = build_system_prompt(ctx)

    messages: list[dict] = []
    for m in ctx.history[-Config.MAX_HISTORY_TURNS:]:
        role = m.get("role", "user") if isinstance(m, dict) else m.role
        content = m.get("content", "") if isinstance(m, dict) else m.content
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": ctx.message})

    # Anthropic requires strict alternation starting with user.
    if messages and messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "Hello"})

    return system_prompt, messages
