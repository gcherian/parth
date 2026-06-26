"""
Signal extraction from student messages — no LLM required.
Fast heuristics that run synchronously before the main Ollama call.
"""
import re
import unicodedata

from pipeline.analogies import detect_domains

# NCERT concept keyword map  (concept_id → detection patterns)
_CONCEPTS: dict[str, set[str]] = {
    "photosynthesis":       {"photosynthesis", "chlorophyll", "chloroplast", "sunlight food"},
    "nutrition_plants":     {"nutrition", "plant food", "autotroph", "heterotroph"},
    "nutrition_animals":    {"digestion", "stomach", "intestine", "enzyme", "amoeba"},
    "cell":                 {"cell", "nucleus", "membrane", "cytoplasm", "organelle"},
    "motion":               {"speed", "velocity", "acceleration", "distance", "displacement"},
    "force":                {"force", "newton", "momentum", "inertia", "friction"},
    "light":                {"reflection", "refraction", "lens", "mirror", "optics", "prism"},
    "electricity":          {"current", "circuit", "resistance", "voltage", "conductor"},
    "combustion":           {"combustion", "flame", "fire", "ignition", "fuel", "oxygen"},
    "matter":               {"matter", "atom", "molecule", "element", "compound", "mixture"},
    "fractions":            {"fraction", "numerator", "denominator", "decimal", "percent"},
    "integers":             {"integer", "negative number", "number line", "absolute value"},
    "algebra":              {"equation", "variable", "algebra", "expression", "polynomial"},
    "geometry":             {"triangle", "angle", "circle", "polygon", "area", "perimeter"},
    "mensuration":          {"volume", "surface area", "mensuration", "cuboid", "cylinder"},
    "french_revolution":    {"french revolution", "bastille", "liberty", "napoleon", "estates"},
    "nationalism":          {"nationalism", "nation state", "colonialism", "independence"},
    "geography_india":      {"india", "latitude", "longitude", "tropic", "peninsula", "plateau"},
    "water_cycle":          {"evaporation", "condensation", "precipitation", "water cycle"},
    "ecosystem":            {"ecosystem", "food chain", "habitat", "predator", "prey"},
}

# Devanagari Unicode range
_DEVANAGARI = re.compile(r'[ऀ-ॿ]')

# Frustration / confusion signals
_CONFUSION_RE = re.compile(
    r"don'?t (get|understand)|not (getting|understanding)|i'?m? ?stuck|"
    r"what does .+ mean|i don'?t know|help me|confused|make no sense",
    re.IGNORECASE,
)
_EXCITEMENT_RE = re.compile(r'[!]{2,}|wow|amazing|cool|awesome|great', re.IGNORECASE)


def extract(message: str) -> dict:
    """
    Returns a signals dict:
      language_ratio: float  (1.0 = all English, 0.0 = all Hindi)
      concepts: list[str]    concept_ids detected
      domains: list[str]     analogy domains detected
      emotion_hint: str      heuristic pre-filter for emotion
      word_count: int
    """
    words = message.split()
    word_count = len(words)
    total_chars = max(1, sum(len(w) for w in words))
    deva_chars = len(_DEVANAGARI.findall(message))

    language_ratio = max(0.0, 1.0 - (deva_chars / total_chars))

    lower = message.lower()
    concepts = [cid for cid, kws in _CONCEPTS.items() if any(k in lower for k in kws)]
    domains = detect_domains(message)

    # Heuristic emotion pre-filter (validated / overridden by LLM evaluator)
    if _CONFUSION_RE.search(message):
        emotion_hint = "confused"
    elif _EXCITEMENT_RE.search(message):
        emotion_hint = "excited"
    elif word_count < 5 and not message.endswith('?'):
        emotion_hint = "disengaged"
    elif message.endswith('?') or message.count('?') > 1:
        emotion_hint = "curious"
    else:
        emotion_hint = "neutral"

    return {
        "language_ratio": round(language_ratio, 3),
        "concepts": concepts,
        "domains": domains,
        "emotion_hint": emotion_hint,
        "word_count": word_count,
    }
