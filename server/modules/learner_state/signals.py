"""Fast heuristic signal extraction — no LLM calls."""
import re
import unicodedata

# Concept keyword map — NCERT-aligned concept IDs
_CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "photosynthesis":     ["photosynthesis", "chlorophyll", "chloroplast", "sunlight plant", "food plant"],
    "cell_biology":       ["cell", "nucleus", "mitochondria", "ribosome", "membrane"],
    "fractions":          ["fraction", "numerator", "denominator", "half", "quarter", "1/2", "3/4"],
    "algebra_basics":     ["equation", "variable", "algebra", "solve for x", "unknown"],
    "newton_laws":        ["force", "newton", "gravity", "acceleration", "mass", "inertia"],
    "water_cycle":        ["evaporation", "condensation", "precipitation", "water cycle", "rain cloud"],
    "mughal_empire":      ["mughal", "akbar", "aurangzeb", "babur", "delhi sultanate"],
    "indian_independence":["independence", "freedom fighter", "gandhi", "british", "1947"],
    "arithmetic":         ["add", "subtract", "multiply", "divide", "sum", "product", "quotient"],
    "geometry":           ["triangle", "circle", "square", "rectangle", "angle", "perimeter", "area"],
    "electricity":        ["circuit", "current", "voltage", "resistance", "battery", "bulb"],
    "human_body":         ["heart", "lung", "blood", "digestive", "nervous", "skeleton"],
    "ecosystem":          ["ecosystem", "food chain", "habitat", "predator", "prey"],
    "magnetism":          ["magnet", "magnetic", "north pole", "south pole", "compass"],
    "light_optics":       ["reflection", "refraction", "lens", "mirror", "prism", "rainbow"],
    "sound":              ["sound", "vibration", "frequency", "wavelength", "echo"],
    "periodic_table":     ["element", "atom", "molecule", "periodic", "hydrogen", "oxygen", "carbon"],
    "bodmas":             ["bodmas", "bracket", "order of operations", "pemdas"],
    "decimals":           ["decimal", "0.", "hundredths", "tenths", "place value"],
    "ratios":             ["ratio", "proportion", "rate", "per cent", "percent", "%"],
}

# Analogy domains
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "cricket":   ["cricket", "bat", "wicket", "six", "four", "run", "bowler", "ipl", "virat"],
    "cooking":   ["cook", "recipe", "roti", "dal", "sabzi", "spice", "kitchen", "boil", "fry"],
    "festival":  ["diwali", "holi", "eid", "christmas", "navratri", "puja", "celebration"],
    "nature":    ["tree", "leaf", "river", "mountain", "cloud", "rain", "flower", "bird"],
    "transport": ["bus", "auto", "train", "car", "rickshaw", "metro", "bicycle"],
    "gaming":    ["game", "level", "score", "player", "win", "lose", "video game", "phone game"],
    "farming":   ["farm", "crop", "field", "wheat", "paddy", "kisan", "harvest", "soil"],
}

# Emotion patterns — checked in priority order; frustrated/distressed detected first
# Must match EmotionCompass._NEGATIVE and evaluator._PROMPT emotion vocab exactly.
_EMOTION_PATTERNS = {
    "frustrated":  r"\b(frustrated|i give up|give up|too hard|can't do|cant do|impossible|"
                   r"nahi kar sakta|nahi samajh|bahut mushkil|this is hard|so hard|fed up|ugh)\b",
    "distressed":  r"\b(distressed|panicking|scared|failing|going to fail|will fail|"
                   r"dar lag raha|stress|stressed out|crying|want to cry)\b",
    "anxious":     r"\b(anxious|worried|nervous|what if i fail|exam kal hai|kal exam|tension)\b",
    "confused":    r"\b(confused|don't understand|don't get|kya matlab|samjha nahi|what is|why is|how does)\b",
    "curious":     r"\b(what if|can we|tell me more|why does|how come|and then|next|more)\b",
    "excited":     r"\b(wow|amazing|awesome|great|maza|cool!|love this|so interesting|incredible)\b",
    "disengaged":  r"\b(boring|don't care|whatever|bakwas|don't want|hate (this|math|science))\b",
}

_EMOTION_RE = {k: re.compile(v, re.IGNORECASE) for k, v in _EMOTION_PATTERNS.items()}
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def extract(message: str) -> dict:
    words = message.lower()

    # Language ratio: fraction of non-space chars that are Devanagari
    devanagari_chars = len(_DEVANAGARI_RE.findall(message))
    total_chars = max(1, len(message.replace(" ", "")))
    language_ratio = 1.0 - (devanagari_chars / total_chars)  # 1.0 = English, 0.0 = Hindi

    # Concepts mentioned
    concepts = [
        cid for cid, keywords in _CONCEPT_KEYWORDS.items()
        if any(kw in words for kw in keywords)
    ]

    # Analogy domains mentioned
    domains = [
        did for did, keywords in _DOMAIN_KEYWORDS.items()
        if any(kw in words for kw in keywords)
    ]

    # Emotion hint
    emotion_hint = "neutral"
    for emotion, pattern in _EMOTION_RE.items():
        if pattern.search(message):
            emotion_hint = emotion
            break

    return {
        "language_ratio": round(language_ratio, 3),
        "concepts": concepts,
        "domains": domains,
        "emotion_hint": emotion_hint,
        "word_count": len(message.split()),
    }
