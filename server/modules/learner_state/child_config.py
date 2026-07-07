"""
Per-child agent configuration.

Design
------
Every agent in the learner harness reads from global Config.* constants.
This module adds a per-child override layer: a guardian (or the BMAD onboarding
agent) can adjust any of these parameters for a specific child without touching
global defaults.

Runtime lookup is intentionally a simple cache: load once per session from
child_agent_config + child_global_config, merge with global Config fallbacks,
return a flat dict to the agent.

Agents use it like:
    cfg = await child_config.load(conn, signals.learner_id)
    threshold = cfg.agent("mastery_tracker").get("weak_threshold", Config.MASTERY_WEAK_THRESHOLD)

AGENT_SCHEMA is the canonical reference for every valid config key per agent.
  type        — Python type used for validation ('float','int','bool','str','enum','list')
  default     — value used when no per-child override exists (should match Config.*)
  description — shown to guardians in settings UI
  guardian_visible — whether the guardian can edit this (some are system-only)

ONBOARDING_QUESTIONS maps guardian questions to the agent config keys they inform.
The BMAD onboarding LLM reads these to produce an initial child_agent_config.
"""
from __future__ import annotations

from config import Config

# ── Canonical config schema per agent ─────────────────────────────────────────
# Keys not listed here are ignored by the config loader (no arbitrary injection).

AGENT_SCHEMA: dict[str, dict[str, dict]] = {

    "emotion_compass": {
        "distress_sensitivity": {
            "type": "enum", "values": ["high", "normal", "low"], "default": "normal",
            "description": "How quickly Parth flags distress signals.",
            "guardian_visible": True,
        },
    },

    "mastery_tracker": {
        "strong_threshold": {
            "type": "float", "min": 0.4, "max": 0.95, "default": Config.MASTERY_STRONG_THRESHOLD,
            "description": "Bayesian mastery probability required before calling a concept 'strong'.",
            "guardian_visible": False,
        },
        "weak_threshold": {
            "type": "float", "min": 0.05, "max": 0.5, "default": Config.MASTERY_WEAK_THRESHOLD,
            "description": "Below this probability the concept is flagged as weak.",
            "guardian_visible": False,
        },
    },

    "misconception_hunter": {
        "evidence_required": {
            "type": "int", "min": 1, "max": 5, "default": Config.MISCONCEPTION_EVIDENCE,
            "description": "Number of matching wrong answers before a misconception is flagged.",
            "guardian_visible": True,
        },
        "watch_concepts": {
            "type": "list", "item_type": "str", "default": [],
            "description": "Concept IDs the guardian wants extra vigilance on (e.g. 'fractions').",
            "guardian_visible": True,
        },
    },

    "language_bridge": {
        "policy": {
            "type": "enum", "values": ["auto", "english", "hindi", "hinglish"], "default": "auto",
            "description": "Language Parth should use. 'auto' detects from each message.",
            "guardian_visible": True,
        },
        "hindi_threshold": {
            "type": "float", "min": 0.0, "max": 1.0, "default": 0.7,
            "description": "Devanagari ratio below which the session is classified as Hindi-preferred.",
            "guardian_visible": False,
        },
    },

    "belief_coach": {
        "min_samples": {
            "type": "int", "min": 2, "max": 15, "default": Config.PSYCHE_MIN_SAMPLES,
            "description": "Minimum interactions before drawing confidence/mindset conclusions.",
            "guardian_visible": False,
        },
        "target_mindset": {
            "type": "enum", "values": ["growth", "performance"], "default": "growth",
            "description": "What Parth reinforces: growth (effort) or performance (results).",
            "guardian_visible": True,
        },
    },

    "challenge_calibrator": {
        "base_difficulty": {
            "type": "enum", "values": ["easy", "medium", "hard"], "default": "medium",
            "description": "Starting difficulty for topics the child hasn't seen before.",
            "guardian_visible": True,
        },
        "productive_failure": {
            "type": "bool", "default": True,
            "description": "Allow a period of productive struggle before simplifying (Kapur 2016).",
            "guardian_visible": True,
        },
        "max_frustration_turns": {
            "type": "int", "min": 1, "max": 5, "default": 2,
            "description": "How many consecutive frustrated messages before Parth reduces difficulty.",
            "guardian_visible": True,
        },
    },

    "learning_velocity": {
        "strong_threshold": {
            "type": "float", "min": 0.4, "max": 0.95, "default": Config.MASTERY_STRONG_THRESHOLD,
            "description": "Mastery probability used as the destination for time-to-mastery estimates.",
            "guardian_visible": False,
        },
        "weak_threshold": {
            "type": "float", "min": 0.05, "max": 0.5, "default": Config.MASTERY_WEAK_THRESHOLD,
            "description": "Lower bound of the ZPD band used to normalize learning velocity.",
            "guardian_visible": False,
        },
    },

    "motivation_drive": {
        "return_window_days": {
            "type": "int", "min": 1, "max": 14, "default": 7,
            "description": "Window for counting a return after a difficult turn.",
            "guardian_visible": False,
        },
    },

    "memory_keeper": {
        "sm2_initial_ease": {
            "type": "float", "min": 1.3, "max": 3.0, "default": 2.5,
            "description": "SM-2 ease factor. Higher = reviewed less frequently.",
            "guardian_visible": False,
        },
        "review_frequency": {
            "type": "enum", "values": ["daily", "weekly", "adaptive"], "default": "adaptive",
            "description": "How often old topics resurface in Parth's prompts.",
            "guardian_visible": True,
        },
    },

    "transfer_weaver": {
        "preferred_domains": {
            "type": "list",
            "item_type": "enum",
            "values": ["cricket", "cooking", "gaming", "farming", "festival", "nature", "transport"],
            "default": [],
            "description": "Analogy domains the child connects with (empty = auto-detect).",
            "guardian_visible": True,
        },
        "avoid_domains": {
            "type": "list",
            "item_type": "enum",
            "values": ["cricket", "cooking", "gaming", "farming", "festival", "nature", "transport"],
            "default": [],
            "description": "Analogy domains to never use for this child.",
            "guardian_visible": True,
        },
        "retirement_score": {
            "type": "float", "min": 0.3, "max": 1.0, "default": Config.ANALOGY_RETIREMENT_SCORE,
            "description": "Mastery score above which an analogy is retired (child has outgrown it).",
            "guardian_visible": False,
        },
    },

    "register_tuner": {
        "formality": {
            "type": "enum", "values": ["formal", "neutral", "casual"], "default": "neutral",
            "description": "How formal Parth's language should be.",
            "guardian_visible": True,
        },
        "sentence_complexity": {
            "type": "enum", "values": ["simple", "normal", "complex"], "default": "normal",
            "description": "Sentence length and vocabulary complexity.",
            "guardian_visible": True,
        },
    },

    "humor_delight_guide": {
        "humor_enabled": {
            "type": "bool", "default": True,
            "description": "Allow Parth to use light humour and playful language.",
            "guardian_visible": True,
        },
        "initial_tolerance": {
            "type": "float", "min": 0.0, "max": 1.0, "default": 0.5,
            "description": "Starting humour level (0 = none, 1 = maximum).",
            "guardian_visible": True,
        },
        "nogo_topics": {
            "type": "list",
            "item_type": "enum",
            "values": ["religion", "caste", "appearance", "family", "politics"],
            "default": ["religion", "caste", "appearance"],
            "description": "Topics Parth must never joke about for this child.",
            "guardian_visible": True,
        },
    },

    "family_alliance": {
        "caregiver_reports": {
            "type": "bool", "default": False,
            "description": "Send weekly progress reports to the guardian.",
            "guardian_visible": True,
        },
        "report_language": {
            "type": "enum", "values": ["english", "hindi"], "default": "english",
            "description": "Language for guardian progress reports.",
            "guardian_visible": True,
        },
        "caregiver_context": {
            "type": "str", "max_length": 500, "default": "",
            "description": "Any context about the home environment Parth should be aware of.",
            "guardian_visible": True,
        },
    },

    "social_preference": {
        "peer_prompts_enabled": {
            "type": "bool", "default": False,
            "description": "Allow optional peer-style or teach-back prompts when social preference is strong.",
            "guardian_visible": True,
        },
    },

    "rhythm_time_steward": {
        "study_start_hour": {
            "type": "int", "min": 5, "max": 23, "default": 16,
            "description": "Hour (24h) when the child typically starts studying.",
            "guardian_visible": True,
        },
        "session_max_minutes": {
            "type": "int", "min": 15, "max": 120, "default": 45,
            "description": "Maximum session length before Parth suggests a break.",
            "guardian_visible": True,
        },
    },

    "inquiry_alchemist": {
        "sel_mode": {
            "type": "enum", "values": ["active", "passive", "off"], "default": "passive",
            "description": "Social-emotional learning: active (Parth initiates SEL), passive (only when relevant), off.",
            "guardian_visible": True,
        },
    },

    "pattern_creation_guide": {
        "wonder_frequency": {
            "type": "enum", "values": ["always", "sometimes", "rarely"], "default": "sometimes",
            "description": "How often Parth poses big 'wonder questions' across domains.",
            "guardian_visible": True,
        },
        "cross_domain_enabled": {
            "type": "bool", "default": True,
            "description": "Allow Parth to connect topics across subjects (e.g. DNA = computer storage).",
            "guardian_visible": True,
        },
    },
}

# Global config (applies across all agents)
GLOBAL_SCHEMA: dict[str, dict] = {
    "exam_prep_mode": {
        "type": "bool", "default": False,
        "description": "Exam preparation mode — Parth focuses on syllabus, minimises tangents.",
        "guardian_visible": True,
    },
    "exam_date": {
        "type": "date", "default": None,
        "description": "Date of the next important exam (ISO 8601: YYYY-MM-DD).",
        "guardian_visible": True,
    },
    "max_response_words": {
        "type": "int", "min": 50, "max": 500, "default": 200,
        "description": "Target maximum length for Parth's responses.",
        "guardian_visible": True,
    },
    "session_persona": {
        "type": "enum", "values": ["auto", "encouraging", "socratic", "direct", "playful"],
        "default": "auto",
        "description": "Teaching persona. 'auto' selects based on the child's state.",
        "guardian_visible": True,
    },
}

# ── Onboarding questions → config key mapping ─────────────────────────────────
# The BMAD onboarding LLM reads these questions, collects guardian responses,
# and produces a JSON mapping each question_id to the agent config it informs.
# This is the contract between the onboarding conversation and the runtime agents.

ONBOARDING_QUESTIONS: list[dict] = [
    {
        "id":      "language",
        "text":    "What language does your child prefer for studying? (English / Hindi / Mixed Hinglish)",
        "informs": [("language_bridge", "policy")],
    },
    {
        "id":      "subject_strength",
        "text":    "Which subjects does your child find easiest and hardest?",
        "informs": [],  # Used to pre-populate mastery priors, handled by onboarding module
    },
    {
        "id":      "analogy_domains",
        "text":    "What does your child love outside school? (sports, cooking, gaming, farming, travel...)",
        "informs": [("transfer_weaver", "preferred_domains")],
    },
    {
        "id":      "confidence",
        "text":    "How would you describe your child's confidence in academics?",
        "informs": [("belief_coach", "target_mindset"), ("challenge_calibrator", "base_difficulty")],
    },
    {
        "id":      "humor",
        "text":    "Is your child okay with light humour and playfulness from Parth?",
        "informs": [("humor_delight_guide", "humor_enabled"), ("humor_delight_guide", "initial_tolerance")],
    },
    {
        "id":      "study_time",
        "text":    "What time of day does your child usually study? (morning / afternoon / evening / night)",
        "informs": [("rhythm_time_steward", "study_start_hour")],
    },
    {
        "id":      "session_length",
        "text":    "How long can your child focus before needing a break? (15 / 30 / 45 / 60 minutes)",
        "informs": [("rhythm_time_steward", "session_max_minutes")],
    },
    {
        "id":      "exam_prep",
        "text":    "Is your child currently preparing for an important exam? If yes, when is it?",
        "informs": [("_global", "exam_prep_mode"), ("_global", "exam_date")],
    },
    {
        "id":      "struggle_style",
        "text":    "When stuck, does your child prefer to struggle a bit before getting help, or get help immediately?",
        "informs": [("challenge_calibrator", "productive_failure"), ("challenge_calibrator", "max_frustration_turns")],
    },
    {
        "id":      "report_preference",
        "text":    "Would you like weekly progress reports? In which language?",
        "informs": [("family_alliance", "caregiver_reports"), ("family_alliance", "report_language")],
    },
    {
        "id":      "caregiver_context",
        "text":    "Is there anything about your child's home environment or situation Parth should know?",
        "informs": [("family_alliance", "caregiver_context")],
    },
    {
        "id":      "no_go_topics",
        "text":    "Are there any topics you'd like Parth to never reference, even as jokes? (e.g. religion, family situations)",
        "informs": [("humor_delight_guide", "nogo_topics")],
    },
]

# ── Runtime config loader ─────────────────────────────────────────────────────

class ChildConfig:
    """
    Merged view of per-child overrides + global Config defaults.

    Built once per request (in BaseAgent.observe / read) via load().
    Agents call .agent(name).get(key, fallback) rather than accessing
    Config.* directly, so per-child overrides take effect automatically.
    """

    def __init__(self, agent_rows: dict[str, dict], global_row: dict):
        self._agents = agent_rows   # {agent_name: {key: value, ...}}
        self._global = global_row   # {key: value, ...}

    def agent(self, name: str) -> dict:
        """Return merged config for a named agent (override layer on top of AGENT_SCHEMA defaults)."""
        defaults = {k: v["default"] for k, v in AGENT_SCHEMA.get(name, {}).items()}
        return {**defaults, **self._agents.get(name, {})}

    def glob(self) -> dict:
        """Return global config (exam_prep_mode, persona, etc.)."""
        defaults = {k: v["default"] for k, v in GLOBAL_SCHEMA.items()}
        return {**defaults, **self._global}


async def load(conn, learner_id: str) -> ChildConfig:
    """
    Load per-child config from DB for a single request.
    Called by BaseAgent.get_config(); result is not cached across requests
    so guardian changes take effect immediately.
    """
    agent_rows: dict[str, dict] = {}
    global_row: dict = {}

    try:
        rows = await conn.fetch(
            "SELECT agent_name, config FROM learner_state.child_agent_config WHERE learner_id = $1",
            learner_id,
        )
        for row in rows:
            agent_rows[row["agent_name"]] = dict(row["config"])

        grow = await conn.fetchrow(
            "SELECT exam_prep_mode, exam_date, max_response_words, session_persona "
            "FROM learner_state.child_global_config WHERE learner_id = $1",
            learner_id,
        )
        if grow:
            global_row = dict(grow)
    except Exception:
        pass  # Tables may not exist yet; callers get pure defaults

    return ChildConfig(agent_rows, global_row)


def guardian_visible_schema() -> dict:
    """Return only the guardian-visible keys per agent — for the settings UI."""
    return {
        agent: {
            key: {k: v for k, v in spec.items() if k != "guardian_visible"}
            for key, spec in keys.items()
            if spec.get("guardian_visible")
        }
        for agent, keys in AGENT_SCHEMA.items()
        if any(s.get("guardian_visible") for s in keys.values())
    }
