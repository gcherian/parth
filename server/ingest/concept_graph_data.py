"""
Static NCERT concept-graph data — relocated verbatim from the old
rag/ingest_graph.py (deleted; its Postgres-seeding phase was redundant
with data/curriculum_seed.sql, which already seeds curriculum_graph
far more thoroughly and runs on every apply_schema()).

Kept here, unexecuted as seed logic, only because main.py's /graph
endpoint imports these two constants as a hardcoded fallback for the
graph-visualization UI when concept_graph.json hasn't been generated yet.
"""

NCERT_CONCEPTS = [
    # Mathematics
    {"id": "arithmetic",         "label": "Arithmetic — Numbers & Operations", "subject": "mathematics", "grade_min": 1, "grade_max": 5,  "description": "Addition, subtraction, multiplication, division and number sense"},
    {"id": "fractions",          "label": "Fractions",                          "subject": "mathematics", "grade_min": 3, "grade_max": 6,  "description": "Parts of a whole: numerator, denominator, equivalent fractions, operations"},
    {"id": "decimals",           "label": "Decimals",                           "subject": "mathematics", "grade_min": 4, "grade_max": 7,  "description": "Base-10 fractions, place value, decimal operations"},
    {"id": "bodmas",             "label": "Order of Operations (BODMAS)",       "subject": "mathematics", "grade_min": 5, "grade_max": 7,  "description": "Brackets, Orders, Division, Multiplication, Addition, Subtraction"},
    {"id": "ratios",             "label": "Ratios & Proportions",               "subject": "mathematics", "grade_min": 6, "grade_max": 8,  "description": "Comparing quantities, direct and inverse proportion, percentages"},
    {"id": "geometry",           "label": "Geometry — Shapes & Measurement",   "subject": "mathematics", "grade_min": 4, "grade_max": 10, "description": "Angles, triangles, circles, area, perimeter, Pythagoras theorem"},
    {"id": "algebra_basics",     "label": "Algebra — Variables & Equations",   "subject": "mathematics", "grade_min": 6, "grade_max": 9,  "description": "Linear equations, variables, expressions, simple inequalities"},
    # Science — Biology
    {"id": "cell_biology",       "label": "Cell Structure & Function",          "subject": "science",     "grade_min": 8, "grade_max": 10, "description": "Cell theory, organelles, prokaryotes vs eukaryotes, cell division"},
    {"id": "photosynthesis",     "label": "Photosynthesis",                     "subject": "science",     "grade_min": 7, "grade_max": 10, "description": "How plants convert sunlight to food using chlorophyll and CO₂"},
    {"id": "human_body",         "label": "Human Body Systems",                 "subject": "science",     "grade_min": 5, "grade_max": 10, "description": "Digestive, circulatory, respiratory, skeletal and nervous systems"},
    {"id": "ecosystem",          "label": "Ecosystems & Food Chains",           "subject": "science",     "grade_min": 6, "grade_max": 10, "description": "Producers, consumers, decomposers, energy flow, biodiversity"},
    {"id": "water_cycle",        "label": "Water Cycle",                        "subject": "science",     "grade_min": 5, "grade_max": 7,  "description": "Evaporation, condensation, precipitation, transpiration"},
    # Science — Physics
    {"id": "newton_laws",        "label": "Newton's Laws of Motion",            "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Inertia, F=ma, action-reaction, gravity and acceleration"},
    {"id": "electricity",        "label": "Electricity & Circuits",             "subject": "science",     "grade_min": 7, "grade_max": 10, "description": "Current, voltage, resistance, Ohm's law, series and parallel circuits"},
    {"id": "magnetism",          "label": "Magnetism & Electromagnetism",       "subject": "science",     "grade_min": 6, "grade_max": 10, "description": "Magnetic fields, poles, electromagnets, motors and generators"},
    {"id": "light_optics",       "label": "Light & Optics",                    "subject": "science",     "grade_min": 8, "grade_max": 10, "description": "Reflection, refraction, lenses, mirrors, the electromagnetic spectrum"},
    {"id": "sound",              "label": "Sound & Waves",                      "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Vibration, frequency, amplitude, pitch, speed of sound, echo"},
    # Science — Chemistry
    {"id": "periodic_table",     "label": "Periodic Table & Elements",          "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Atomic structure, periods and groups, metals and non-metals, bonding"},
    # History
    {"id": "mughal_empire",      "label": "Mughal Empire",                      "subject": "history",     "grade_min": 7, "grade_max": 8,  "description": "Babur to Aurangzeb: administration, culture, architecture, decline"},
    {"id": "indian_independence","label": "Indian Independence Movement",       "subject": "history",     "grade_min": 8, "grade_max": 10, "description": "1857 revolt to 1947: Gandhi, non-cooperation, partition, constitution"},
]

NCERT_EDGES = [
    # Mathematics progression (prerequisite)
    ("arithmetic",     "fractions",      "prerequisite"),
    ("arithmetic",     "geometry",       "prerequisite"),
    ("arithmetic",     "bodmas",         "prerequisite"),
    ("fractions",      "decimals",       "prerequisite"),
    ("fractions",      "bodmas",         "co-requisite"),
    ("fractions",      "ratios",         "prerequisite"),
    ("decimals",       "ratios",         "co-requisite"),
    ("ratios",         "algebra_basics", "prerequisite"),
    ("arithmetic",     "algebra_basics", "prerequisite"),
    # Mathematics leads-to chain
    ("arithmetic",     "fractions",      "leads-to"),
    ("fractions",      "decimals",       "leads-to"),
    ("decimals",       "ratios",         "leads-to"),
    ("ratios",         "algebra_basics", "leads-to"),
    ("geometry",       "algebra_basics", "co-requisite"),
    # Physics dependencies
    ("arithmetic",     "newton_laws",    "prerequisite"),
    ("geometry",       "newton_laws",    "co-requisite"),
    ("newton_laws",    "electricity",    "prerequisite"),
    ("newton_laws",    "light_optics",   "prerequisite"),
    ("newton_laws",    "sound",          "prerequisite"),
    ("electricity",    "magnetism",      "leads-to"),
    ("electricity",    "magnetism",      "co-requisite"),
    ("geometry",       "light_optics",   "co-requisite"),
    # Biology chain
    ("cell_biology",   "photosynthesis", "prerequisite"),
    ("cell_biology",   "human_body",     "prerequisite"),
    ("cell_biology",   "photosynthesis", "leads-to"),
    ("photosynthesis", "ecosystem",      "prerequisite"),
    ("photosynthesis", "ecosystem",      "leads-to"),
    ("water_cycle",    "ecosystem",      "co-requisite"),
    # Chemistry
    ("periodic_table", "electricity",    "co-requisite"),
    # History
    ("mughal_empire",  "indian_independence", "leads-to"),
]
