"""
Analogy domain library.
Maps real-world domains to curriculum concepts and provides
keyword-based detection for preference tracking.
"""

DOMAINS: dict[str, dict] = {
    "cricket": {
        "keywords": {"cricket", "bat", "ball", "wicket", "run", "over", "pitch",
                     "boundary", "innings", "bowler", "fielder", "century"},
        "concepts": {"velocity", "projectile", "friction", "statistics",
                     "probability", "motion", "force"},
    },
    "cooking": {
        "keywords": {"roti", "dal", "chai", "cooker", "boil", "fry", "cook",
                     "recipe", "ingredient", "spice", "heat", "steam", "bake"},
        "concepts": {"heat", "temperature", "fractions", "ratios",
                     "chemical reactions", "mixtures", "states of matter"},
    },
    "festival": {
        "keywords": {"diwali", "holi", "eid", "diya", "firework", "colour",
                     "festival", "lantern", "rangoli", "candle", "light"},
        "concepts": {"light", "optics", "colour", "chemistry", "combustion",
                     "reflection", "refraction"},
    },
    "nature": {
        "keywords": {"monsoon", "rain", "river", "mountain", "cloud", "tree",
                     "flower", "forest", "soil", "wind", "storm", "lake"},
        "concepts": {"water cycle", "evaporation", "ecosystem", "photosynthesis",
                     "weathering", "climate", "food chain"},
    },
    "transport": {
        "keywords": {"auto", "rickshaw", "bus", "train", "bicycle", "scooter",
                     "car", "truck", "metro", "road", "engine", "brake"},
        "concepts": {"force", "friction", "motion", "energy", "fuel",
                     "velocity", "acceleration", "work"},
    },
    "gaming": {
        "keywords": {"game", "phone", "app", "level", "score", "player",
                     "screen", "character", "computer", "video", "points"},
        "concepts": {"probability", "logic", "electricity", "circuits",
                     "binary", "programming", "algorithms"},
    },
    "farming": {
        "keywords": {"crop", "field", "harvest", "seed", "irrigation",
                     "farmer", "soil", "fertiliser", "plough", "kisan"},
        "concepts": {"biology", "soil chemistry", "water", "seasons",
                     "nutrition", "microorganisms", "crop rotation"},
    },
}


def detect_domains(text: str) -> list[str]:
    """Return list of domain IDs whose keywords appear in the text."""
    words = set(text.lower().split())
    found = []
    for domain, data in DOMAINS.items():
        if words & data["keywords"]:
            found.append(domain)
    return found


def top_domains(scores: dict[str, float], n: int = 2) -> list[str]:
    """Return the n highest-scoring domain names."""
    return sorted(scores, key=lambda d: scores[d], reverse=True)[:n]


def domain_concepts(domain: str) -> set[str]:
    return DOMAINS.get(domain, {}).get("concepts", set())
