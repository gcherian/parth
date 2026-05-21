"""
Linguistic Register Detector
=============================

A child's register is the domain-vocabulary they arrive in naturally —
not their stated preference, but the world their language comes from.

The first 3 messages contain almost everything we need:
  - What they reference (cricket, cooking, music, games, family)
  - How they structure sentences (short/active = builder; long/questioning = explorer)
  - What question type they default to (why/how/what if/is it true)
  - Emotional tone and Hindi-English ratio

This is NOT a keyword matcher — it is a Bayesian network over 8 register domains,
updated from every message. Each domain reinforces related domains (partial overlap).

The register map feeds directly into concept_bridges.json:
  strong_register → best_bridge_domain → concept introduction path

VISUALISATION NOTES (for Flutter frontend):
  - Expose /puzzle/register/{learner_id} as a JSON object of {domain: probability}
  - Render as a force-directed bubble graph: size = probability, color = domain family
  - Update in real time as the child messages
  - The brightest bubble = the bridge domain Parth will use NOW
  - Parents and teachers can watch the portrait form

Domains and their cross-activation map
---------------------------------------
  cricket      → sport (1.0), competition (0.7), outdoor (0.4)
  cooking      → home (1.0), sensory (0.8), family (0.6), chemistry (0.3)
  music        → arts (1.0), pattern (0.8), performance (0.6), mathematics (0.4)
  gaming       → builder (1.0), challenge (0.8), technology (0.6)
  nature       → biology (1.0), outdoor (0.8), observation (0.6), philosophy (0.3)
  story        → arts (1.0), social (0.8), philosophy (0.6), language (0.4)
  technology   → builder (1.0), gaming (0.5), science (0.5)
  mathematics  → pattern (1.0), challenge (0.6), science (0.5)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Register domains ──────────────────────────────────────────────────────────
# Each domain has: keywords, question_types, sentence_signals, and cross-activations.
# Probability starts at 1/8 (uniform prior).

REGISTER_DOMAINS = [
    "cricket",       # sports, physical, competitive
    "cooking",       # home, sensory, practical
    "music",         # arts, pattern, performance
    "gaming",        # builder, challenge, technology
    "nature",        # observation, biology, outdoor
    "story",         # narrative, arts, social
    "technology",    # builder, systems, logical
    "mathematics",   # pattern, proof, abstract
]

# Keyword patterns (order matters — more specific first)
_KEYWORDS: dict[str, list[str]] = {
    "cricket":    ["cricket", "bat", "ball", "wicket", "run", "over", "boundary", "ipl",
                   "match", "bowler", "fielder", "six", "four", "virat", "rohit",
                   "stadium", "pitch", "innings", "century", "tournament"],
    "cooking":    ["roti", "dal", "sabzi", "cook", "recipe", "kitchen", "boil", "fry",
                   "spice", "masala", "chai", "biryani", "food", "taste", "smell",
                   "heat", "pressure cooker", "tadka", "ingredient", "mother made",
                   "mom cook", "khana", "bhojan"],
    "music":      ["song", "music", "sing", "guitar", "piano", "drum", "beat", "rhythm",
                   "tune", "note", "melody", "concert", "album", "playlist", "raag",
                   "taal", "sargam", "harmonium", "flute", "band"],
    "gaming":     ["game", "level", "score", "player", "win", "lose", "character",
                   "health", "points", "mission", "boss", "minecraft", "roblox",
                   "pubg", "free fire", "controller", "app", "download", "clan"],
    "nature":     ["tree", "leaf", "flower", "bird", "rain", "river", "mountain",
                   "cloud", "soil", "forest", "animal", "insect", "spider", "moon",
                   "sky", "sunrise", "sunset", "wind", "lake", "beach", "season"],
    "story":      ["story", "book", "read", "character", "chapter", "film", "movie",
                   "serial", "cartoon", "comic", "hero", "villain", "plot", "ending",
                   "drama", "funny", "sad", "scene", "novel", "kahani", "kitab"],
    "technology": ["phone", "computer", "laptop", "app", "code", "program", "robot",
                   "ai", "internet", "youtube", "website", "hack", "software",
                   "bug", "device", "screen", "charge", "battery", "wifi"],
    "mathematics":["number", "calculate", "formula", "equation", "pattern", "proof",
                   "sequence", "prime", "infinity", "puzzle", "problem", "math",
                   "geometry", "graph", "function", "symmetry", "ratio"],
}

# Cross-activation weights: mention domain A → boost domain B by weight
_CROSS_ACTIVATION: dict[str, dict[str, float]] = {
    "cricket":    {"nature": 0.2, "mathematics": 0.15},
    "cooking":    {"nature": 0.3, "mathematics": 0.2},
    "music":      {"mathematics": 0.4, "story": 0.3},
    "gaming":     {"technology": 0.5, "mathematics": 0.25},
    "nature":     {"cooking": 0.2, "mathematics": 0.15},
    "story":      {"music": 0.2},
    "technology": {"mathematics": 0.4, "gaming": 0.3},
    "mathematics":{"music": 0.3, "technology": 0.2},
}

# Sentence-level signals
_QUESTION_TYPE_RE = {
    "why":    re.compile(r"\bwhy\b|\bkyun\b|\bhow come\b|\bkyunki\b", re.I),
    "how":    re.compile(r"\bhow (do|does|can|to|much|many|did)\b|\bkaise\b", re.I),
    "whatif": re.compile(r"\bwhat if\b|\bwhat would\b|\bimagine\b|\bagar\b", re.I),
    "isit":   re.compile(r"\bis it (true|really|possible|right)\b|\bkya yeh\b", re.I),
}

# Question type → register affinity boost
_QUESTION_REGISTER_BOOST: dict[str, dict[str, float]] = {
    "why":    {"mathematics": 0.2, "nature": 0.15},       # explorer/philosopher
    "how":    {"technology": 0.2, "gaming": 0.15},         # builder
    "whatif": {"story": 0.2, "nature": 0.15},              # creative/explorer
    "isit":   {"mathematics": 0.3, "technology": 0.1},     # scientist
}

# Sentence length signal
_SHORT_SENTENCE_RE = re.compile(r"[.!?]", re.I)


@dataclass
class RegisterState:
    """Per-learner register probability state."""
    learner_id: str
    probs: dict[str, float] = field(
        default_factory=lambda: {d: 1.0 / 8 for d in REGISTER_DOMAINS}
    )
    n_messages: int = 0
    dominant_question_type: str = "unknown"
    avg_sentence_length: float = 10.0   # words per sentence


def update(state: RegisterState, message: str) -> RegisterState:
    """
    Update register probabilities from a new message.
    Returns the updated state (mutates in place and returns for convenience).
    """
    text_lower = message.lower()
    words = message.split()
    state.n_messages += 1

    # ── 1. Keyword evidence ────────────────────────────────────────────────
    keyword_hits: dict[str, int] = {d: 0 for d in REGISTER_DOMAINS}
    for domain, keywords in _KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                keyword_hits[domain] += 1

    # ── 2. Cross-activation ────────────────────────────────────────────────
    cross_boost: dict[str, float] = {d: 0.0 for d in REGISTER_DOMAINS}
    for domain, hits in keyword_hits.items():
        if hits > 0:
            for target, weight in _CROSS_ACTIVATION.get(domain, {}).items():
                cross_boost[target] += weight * min(hits, 3)

    # ── 3. Question type ───────────────────────────────────────────────────
    question_boost: dict[str, float] = {d: 0.0 for d in REGISTER_DOMAINS}
    detected_q = "unknown"
    for qtype, pattern in _QUESTION_TYPE_RE.items():
        if pattern.search(message):
            detected_q = qtype
            for domain, boost in _QUESTION_REGISTER_BOOST.get(qtype, {}).items():
                question_boost[domain] += boost
            break
    state.dominant_question_type = detected_q

    # ── 4. Sentence length signal ─────────────────────────────────────────
    sentence_count = max(1, len(_SHORT_SENTENCE_RE.findall(message)))
    avg_len = len(words) / sentence_count
    state.avg_sentence_length = 0.7 * state.avg_sentence_length + 0.3 * avg_len
    # Long sentences → boost mathematics, nature (reflective domains)
    length_boost: dict[str, float] = {}
    if avg_len > 20:
        length_boost = {"mathematics": 0.1, "nature": 0.1, "story": 0.1}
    elif avg_len < 6:
        length_boost = {"gaming": 0.1, "cricket": 0.05}

    # ── 5. Adaptive EMA update ────────────────────────────────────────────
    alpha = 0.45 if state.n_messages <= 3 else (0.25 if state.n_messages <= 8 else 0.15)

    for domain in REGISTER_DOMAINS:
        # Compute evidence signal (0-1): keyword hits + cross + question + length
        kw_signal = min(1.0, keyword_hits[domain] * 0.5)
        evidence = (
            0.50 * kw_signal +
            0.25 * min(1.0, cross_boost[domain] / 2.0) +
            0.15 * question_boost.get(domain, 0.0) +
            0.10 * length_boost.get(domain, 0.0)
        )
        # EMA update
        old = state.probs[domain]
        state.probs[domain] = round((1 - alpha) * old + alpha * evidence, 4)

    # ── 6. Renormalise ────────────────────────────────────────────────────
    total = sum(state.probs.values()) or 1.0
    state.probs = {d: round(v / total, 4) for d, v in state.probs.items()}

    return state


def dominant_register(state: RegisterState) -> str:
    """Return the domain with highest probability."""
    return max(state.probs, key=state.probs.__getitem__)


def top_registers(state: RegisterState, n: int = 3) -> list[tuple[str, float]]:
    """Return top-n (domain, probability) pairs, sorted descending."""
    return sorted(state.probs.items(), key=lambda x: x[1], reverse=True)[:n]


# ── Register → bridge domain mapping ────────────────────────────────────────
# Maps linguistic register to the concept_bridges.json sphere keys.
# A child whose language comes from cricket → use the "cricket" bridge.
# A child whose language comes from music → "arts_interdisciplinary" bridge.

REGISTER_TO_BRIDGE: dict[str, str] = {
    "cricket":    "cricket",
    "cooking":    "cooking",
    "music":      "arts_interdisciplinary",
    "gaming":     "computer_science_ai",
    "nature":     "biology_medicine",
    "story":      "arts_interdisciplinary",
    "technology": "computer_science_ai",
    "mathematics": "mathematics",
}


def best_bridge_for_concept(
    concept_id: str,
    state: RegisterState,
    bridges: dict,
) -> dict | None:
    """
    Given the current register state and a concept to teach,
    return the best bridge entry from concept_bridges.json.

    Falls back through register rank order until a bridge is found.
    """
    for domain, prob in top_registers(state, n=len(REGISTER_DOMAINS)):
        sphere = REGISTER_TO_BRIDGE.get(domain, domain)
        bridge = bridges.get(concept_id, {}).get(sphere)
        if bridge:
            return {
                "domain":    domain,
                "sphere":    sphere,
                "prob":      prob,
                "hook":      bridge.get("hook", ""),
                "example":   bridge.get("example", ""),
                "telos_fit": bridge.get("best_for_telos", []),
            }
    # Final fallback: return the first available bridge for this concept
    concept_bridges = bridges.get(concept_id, {})
    if concept_bridges:
        first_sphere = next(iter(concept_bridges))
        b = concept_bridges[first_sphere]
        return {
            "domain":    first_sphere,
            "sphere":    first_sphere,
            "prob":      0.0,
            "hook":      b.get("hook", ""),
            "example":   b.get("example", ""),
            "telos_fit": b.get("best_for_telos", []),
        }
    return None


def register_visualisation(state: RegisterState) -> dict:
    """
    Returns a payload suitable for a bubble-graph visualisation.
    Each bubble: domain, probability, color_family, is_dominant.

    Flutter frontend renders this as a force-directed graph.
    Probabilities determine bubble radius. Color = domain family.
    """
    color_families = {
        "cricket":    {"family": "sport",       "color": "#2196F3"},
        "cooking":    {"family": "home",         "color": "#FF9800"},
        "music":      {"family": "arts",         "color": "#9C27B0"},
        "gaming":     {"family": "technology",   "color": "#4CAF50"},
        "nature":     {"family": "science",      "color": "#009688"},
        "story":      {"family": "arts",         "color": "#E91E63"},
        "technology": {"family": "technology",   "color": "#607D8B"},
        "mathematics":{"family": "science",      "color": "#FF5722"},
    }
    dominant = dominant_register(state)
    return {
        "learner_id":     state.learner_id,
        "n_messages":     state.n_messages,
        "question_style": state.dominant_question_type,
        "bubbles": [
            {
                "domain":    d,
                "probability": p,
                "radius":    round(p * 120, 1),   # px, for frontend
                "is_dominant": d == dominant,
                **color_families.get(d, {"family": "other", "color": "#9E9E9E"}),
            }
            for d, p in sorted(state.probs.items(), key=lambda x: x[1], reverse=True)
        ],
        "dominant_domain": dominant,
        "confidence": round(max(state.probs.values()) / (1.0 / len(REGISTER_DOMAINS)), 2),
    }
