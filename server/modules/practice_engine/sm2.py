"""
SM-2 spaced repetition algorithm.
quality: 0-5 (0=complete blackout, 3=correct with difficulty, 5=perfect recall)
"""
from datetime import datetime, timedelta


def update_card(
    repetitions: int,
    interval_days: float,
    ease_factor: float,
    quality: int,
) -> tuple[int, float, float]:
    """
    Returns (new_repetitions, new_interval_days, new_ease_factor).
    """
    quality = max(0, min(5, quality))

    if quality < 3:
        # Failed recall — reset
        new_reps = 0
        new_interval = 1.0
    else:
        if repetitions == 0:
            new_interval = 1.0
        elif repetitions == 1:
            new_interval = 6.0
        else:
            new_interval = interval_days * ease_factor
        new_reps = repetitions + 1

    # Update ease factor (minimum 1.3 to avoid very short intervals)
    new_ef = ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    new_ef = max(1.3, new_ef)

    return new_reps, round(new_interval, 2), round(new_ef, 3)


def quality_from_correct(correct: bool, was_hint_used: bool = False) -> int:
    """Convert a simple correct/incorrect answer to SM-2 quality score."""
    if correct and not was_hint_used:
        return 4
    if correct:
        return 3
    return 2
