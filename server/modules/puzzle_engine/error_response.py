"""
Error Response Classifier
=========================

Classifies a child's reaction to difficulty into four patterns.
This is the single richest behavioural signal in limited interactions —
each pattern requires a completely different tutor response.

GROWTH       → tries again; "let me think"; explores alternatives
FIXED        → "I can't"; gives up; ability attribution
AVOIDANT     → changes subject; "this is boring"; redirects
PERFECTIONIST → "I got one part wrong"; wants to restart; high anxiety about errors

Classification is heuristic (regex-based, fast, no LLM call).
The LLM evaluator provides a secondary signal for ambiguous cases.
"""
from __future__ import annotations

import re

_GROWTH = re.compile(
    r"\b(let me try|trying again|another way|what if i|oh i see|so if|"
    r"maybe it|let me think|actually wait|hmm|aur try karta|maine socha|"
    r"ok so|try kar|ek aur)\b",
    re.IGNORECASE,
)

_FIXED = re.compile(
    r"\b(i can'?t|can't do|i'?m bad at|not good at|i'?ll never|"
    r"i give up|too hard|impossible|not smart|i don'?t get it|"
    r"never understand|nahi kar sakta|bahut mushkil|mujhse nahi hoga|"
    r"i'?m (dumb|stupid|hopeless))\b",
    re.IGNORECASE,
)

_AVOIDANT = re.compile(
    r"\b(skip|next (question|puzzle|one)|something else|this is boring|"
    r"don'?t (want|like|care)|whatever|bakwas|chhod do|kuch aur|"
    r"can we (do|try)|change topic|move on)\b",
    re.IGNORECASE,
)

_PERFECTIONIST = re.compile(
    r"\b(but i got (part|some|one) wrong|start (over|again)|that'?s not right|"
    r"not exactly|i made a mistake|let me redo|from the beginning|"
    r"that'?s not perfect|i need to redo|phir se|galat ho gaya)\b",
    re.IGNORECASE,
)

# Parth's response strategy per type — injected into context
RESPONSE_STRATEGIES = {
    "growth": (
        "Reinforce the process: 'Good — now here's the harder version.' "
        "Do not over-praise effort. Challenge slightly beyond their comfort zone."
    ),
    "fixed": (
        "NEVER say 'wrong' or 'incorrect'. Say 'not yet'. "
        "Ask what they DID understand before addressing the gap. "
        "Attribute outcomes to strategy: 'That approach didn't work — which one next?' "
        "NEVER praise intelligence ('you're so smart'). Praise process only."
    ),
    "avoidant": (
        "Do not insist on the current puzzle. Follow the child's redirect. "
        "Embed the stuck concept inside their new question — "
        "they will encounter it without realising it's the same idea."
    ),
    "perfectionist": (
        "Reframe immediately: 'Getting one thing wrong means nine things are right — what were the nine?' "
        "Move forward. Do not allow restart loops. Normalise imperfection as the mechanism of learning."
    ),
    "unknown": (
        "No clear signal yet. Use gentle encouragement and observe the next response."
    ),
}


def classify_error_response(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return "avoidant"
    if _FIXED.search(text):
        return "fixed"
    if _PERFECTIONIST.search(text):
        return "perfectionist"
    if _AVOIDANT.search(text):
        return "avoidant"
    if _GROWTH.search(text):
        return "growth"
    return "unknown"


def get_strategy(error_response_type: str) -> str:
    return RESPONSE_STRATEGIES.get(error_response_type, RESPONSE_STRATEGIES["unknown"])
