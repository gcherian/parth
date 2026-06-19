"""
Five natural locations — each a scale-spanning wonder.
Ref: NGSS Appendix G — patterns, scale, proportion, systems thinking
cross-cut every domain. These locations ARE those crosscutting concepts made tangible.
"""
from __future__ import annotations

# The 5 demo students that appear in the Playground
PLAYGROUND_PERSONAS = [
    {
        "id": "arjun_s8",
        "name": "Arjun",
        "grade": 8,
        "subject": "Science",
        "emoji": "🏏",
        "color": "#f97316",
        "tagline": "Cricket-obsessed. Thinks physics is obvious. Gets wonderfully corrected.",
    },
    {
        "id": "sneha_s6",
        "name": "Sneha",
        "grade": 6,
        "subject": "Science",
        "emoji": "🌸",
        "color": "#ec4899",
        "tagline": "Shy and Hindi-dominant. Has sudden brilliant breakthroughs.",
    },
    {
        "id": "dev_s10",
        "name": "Dev",
        "grade": 10,
        "subject": "Mathematics",
        "emoji": "🎮",
        "color": "#22c55e",
        "tagline": "Everything is a game mechanic. Gets bored unless challenged hard.",
    },
    {
        "id": "meera_s7",
        "name": "Meera",
        "grade": 7,
        "subject": "Mathematics",
        "emoji": "📐",
        "color": "#a855f7",
        "tagline": "Says she gives up — then has the breakthrough. Every time.",
    },
    {
        "id": "rishi_s9",
        "name": "Rishi",
        "grade": 9,
        "subject": "Science",
        "emoji": "🌌",
        "color": "#3b82f6",
        "tagline": "Finds the same pattern in DNA, computers, and galaxies. Awe-prone.",
    },
]

# Map learner_id → persona for quick lookup
PERSONA_MAP = {p["id"]: p for p in PLAYGROUND_PERSONAS}


# The 5 natural locations
LOCATIONS: dict[str, dict] = {
    "andromeda": {
        "id": "andromeda",
        "name": "Andromeda Galaxy",
        "emoji": "🌌",
        "tagline": "2.5 million light years away — and falling toward us",
        "bg_from": "#1e1b4b",
        "bg_to": "#0f0a1e",
        "accent": "#818cf8",
        "description": (
            "Andromeda contains over 1 trillion stars and sits 2.537 million light-years away. "
            "It is approaching the Milky Way at 110 km/s — a cosmic collision in 4.5 billion years "
            "that will create a new elliptical galaxy. The light leaving Andromeda right now will "
            "arrive on Earth long after our sun has died."
        ),
        "wonder_hook": (
            "The light you see from Andromeda tonight left before Homo sapiens existed. "
            "You are looking 2.5 million years into the past."
        ),
        "concept_ids": ["light", "scale", "gravity", "speed", "time"],
        "depth_levels": ["Star Field", "Light & Time", "Gravity & Orbits", "Star Nurseries", "Dark Matter Halo"],
        "group_bonus": (
            "Together: Andromeda has ~1 trillion stars, the Milky Way ~300 billion. "
            "If 1 in 5 stars has planets, and 1 in 1000 planets could support life — "
            "calculate how many potential life-worlds exist in just these two galaxies."
        ),
        "solo_opener": (
            "You've arrived at the edge of Andromeda. Before you: a trillion suns, "
            "and the light you're seeing left 2.5 million years ago. What do you want to explore first?"
        ),
    },
    "mariana": {
        "id": "mariana",
        "name": "Mariana Trench",
        "emoji": "🌊",
        "tagline": "11 km down — deeper than Everest is tall",
        "bg_from": "#0c1445",
        "bg_to": "#030918",
        "accent": "#38bdf8",
        "description": (
            "The Mariana Trench reaches 11,034 metres — the deepest point on Earth. "
            "At the Challenger Deep, pressure is 1,086 atmospheres — equivalent to 50 jumbo jets "
            "stacked on a human body. Zero light. Near-freezing temperatures. "
            "Yet snailfish, amphipods, and single-celled organisms thrive here, eating falling 'marine snow'."
        ),
        "wonder_hook": (
            "At the very bottom, the water is actually slightly warmer due to compression heating — "
            "the same physics as a bicycle pump getting warm when you inflate a tyre."
        ),
        "concept_ids": ["pressure", "light", "density", "adaptation", "depth"],
        "depth_levels": ["Sunlight Zone (0-200m)", "Twilight Zone (200-1000m)", "Midnight Zone (1-4km)", "Abyssal Zone (4-6km)", "Hadal Zone (6-11km)"],
        "group_bonus": (
            "Every 10m of water adds approximately 1 atmosphere of pressure. "
            "Calculate together: what is the total pressure at the Challenger Deep (11km)? "
            "Then convert it: how many elephants per square metre is that?"
        ),
        "solo_opener": (
            "You've descended to the Hadal Zone — 11km down, pitch dark, crushing pressure. "
            "Somehow, life exists here. What's the first thing you want to understand?"
        ),
    },
    "amazon": {
        "id": "amazon",
        "name": "Amazon Rainforest",
        "emoji": "🌿",
        "tagline": "20% of Earth's oxygen — made by 40,000 plant species",
        "bg_from": "#052e16",
        "bg_to": "#021a0b",
        "accent": "#4ade80",
        "description": (
            "The Amazon Basin covers 5.5 million km² — larger than India. "
            "It contains 10% of all species on Earth and produces 20% of the planet's oxygen. "
            "A single hectare holds more tree species than all of Europe. "
            "Trees communicate through underground mycorrhizal fungal networks, "
            "sharing nutrients and chemical distress signals — the 'wood wide web'."
        ),
        "wonder_hook": (
            "Amazon trees 'talk' — when attacked by insects, they release chemical signals "
            "through air and through underground fungi, warning neighbouring trees to prepare defences. "
            "A forest is a single connected organism."
        ),
        "concept_ids": ["photosynthesis", "water_cycle", "biodiversity", "food_chains", "osmosis"],
        "depth_levels": ["Emergent Layer (45m+)", "Canopy (30-45m)", "Understory (5-30m)", "Forest Floor", "Root & Fungal Network"],
        "group_bonus": (
            "A single Amazon tree transpires 200 litres of water per day. "
            "The Amazon has ~400 billion trees. Together, calculate how much water "
            "the forest puts into the air daily — then compare it to all of India's river flow."
        ),
        "solo_opener": (
            "You're standing on the forest floor — the canopy is 40 metres above, "
            "blocking 99% of sunlight. Everything around you is alive and connected. "
            "Where do you want to go — up into the canopy, or down into the roots?"
        ),
    },
    "kilauea": {
        "id": "kilauea",
        "name": "Kīlauea Volcano",
        "emoji": "🌋",
        "tagline": "Active right now — building new land from the mantle",
        "bg_from": "#450a0a",
        "bg_to": "#1c0505",
        "accent": "#fb923c",
        "description": (
            "Kīlauea on Hawaii has erupted almost continuously since 1983. "
            "Its lava emerges at 1,170°C — hot enough to melt glass instantly. "
            "As it cools, it creates new basalt rock — literally growing the island. "
            "The Hawaiian island chain was entirely built this process over 70 million years "
            "as the Pacific Plate drifted over a stationary hot spot in the mantle."
        ),
        "wonder_hook": (
            "Every continent was built by volcanoes. The ground beneath any city on Earth "
            "was once molten rock from the mantle. You are standing on recycled seafloor."
        ),
        "concept_ids": ["heat", "pressure", "rock_cycle", "plate_tectonics", "density"],
        "depth_levels": ["Lava Field", "Vent & Crater", "Magma Chamber", "Tectonic Plate", "Mantle (2900km down)"],
        "group_bonus": (
            "Lava flows at 1-3 km/h on a gentle slope. The coast is 8km from the vent. "
            "Calculate: how long before it reaches the sea? Then: each km² of new land "
            "adds ~1km² to the island — if this rate continues, "
            "in how many years does Hawaii double in size?"
        ),
        "solo_opener": (
            "You're at the crater rim — below you, molten rock glows orange at 1,170°C. "
            "This is the planet building itself. What do you want to understand: "
            "the heat, the chemistry, or where this rock came from?"
        ),
    },
    "cell": {
        "id": "cell",
        "name": "Inside a Living Cell",
        "emoji": "🦠",
        "tagline": "The most complex machine in the known universe — 0.006mm wide",
        "bg_from": "#2d1843",
        "bg_to": "#12091c",
        "accent": "#c084fc",
        "description": (
            "Your body contains 37 trillion cells. Each is a city — with power plants "
            "(mitochondria), protein factories (ribosomes), a central library (nucleus "
            "with 3 billion DNA base pairs), and a postal system (endoplasmic reticulum). "
            "Right now, your ribosomes are reading DNA at 50 base pairs per second, "
            "assembling proteins from 20 amino acid 'letters' — following instructions "
            "written 3.8 billion years ago."
        ),
        "wonder_hook": (
            "Your entire DNA, uncoiled, would reach from Earth to the Sun and back 600 times — "
            "yet it fits, perfectly folded, inside a nucleus 0.006mm wide. "
            "The same information-packing problem that engineers solved with hard drives, "
            "evolution solved 3 billion years earlier."
        ),
        "concept_ids": ["dna", "protein_synthesis", "osmosis", "energy", "cell_division"],
        "depth_levels": ["Cell Membrane", "Cytoplasm & Organelles", "Nucleus", "DNA Double Helix", "Base Pair Sequence"],
        "group_bonus": (
            "DNA has ~3 billion base pairs. Your ribosomes read at 50 base pairs/second. "
            "Calculate: how many days would it take to 'read' your entire genome once? "
            "Then: Shannon proved that 4-letter codes can carry as much information as binary. "
            "How does DNA compare to a computer hard drive?"
        ),
        "solo_opener": (
            "You've shrunk to nanometre scale — you're inside a living cell. "
            "Around you: the nuclear envelope, ribosomes humming, mitochondria pulsing. "
            "Do you want to head to the nucleus (DNA) or stay in the cytoplasm (protein factories)?"
        ),
    },
}


def get_location(location_id: str) -> dict | None:
    return LOCATIONS.get(location_id)


def all_locations_summary() -> list[dict]:
    return [
        {
            "id": loc["id"],
            "name": loc["name"],
            "emoji": loc["emoji"],
            "tagline": loc["tagline"],
            "bg_from": loc["bg_from"],
            "accent": loc["accent"],
            "depth_levels": loc["depth_levels"],
        }
        for loc in LOCATIONS.values()
    ]
