from config import Config

_COMPLEX = {"why", "how", "explain", "difference", "compare", "derive", "prove",
            "analyze", "analyse", "describe", "discuss", "elaborate", "what if"}


def pick_model(message: str, history_len: int, requested_model: str | None) -> str:
    """Route simple short questions to the fast model; complex ones to the main model."""
    if requested_model:
        return requested_model
    words = message.lower().split()
    is_short = len(words) < 10
    is_simple = not any(w in _COMPLEX for w in words)
    if is_short and is_simple and history_len < 4:
        return Config.FAST_MODEL
    return Config.DEFAULT_MODEL
