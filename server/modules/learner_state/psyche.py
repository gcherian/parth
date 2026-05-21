"""
Learner Psyche — Inferred Psychological Dimensions for Adaptive Pedagogy
========================================================================

Seven dimensions inferred from natural conversation — no questionnaire.
Five are evidence-based for direct pedagogy; two map to MBTI for parent communication.

Evidence base
-------------
1. Conscientiousness (Big Five)   — Poropat (2009) meta-analysis N>70,000 → MBTI J/P
2. Learning Anxiety (Neuroticism) — Hembree (1990) test-anxiety meta-analysis
3. Growth vs Fixed Mindset        — Yeager et al. (2019) N=12,490 national study
4. Depth Preference (NFC)         — Richardson et al. meta-analysis r=.20
5. Mastery Orientation            — Elliot & McGregor (2001) Achievement Goal Theory
6. Extroversion (Big Five)        — DeYoung (2015); social energy → MBTI E/I
7. Thinking vs Feeling (Big Five  — Agreeableness inverse; logic vs values → MBTI T/F
   Agreeableness inverse)

MBTI as communication layer
----------------------------
MBTI is NOT used to drive pedagogy (poor clinical reliability). It IS used as a
parent-facing vocabulary layer — parents understand "your child is an INTJ Mastermind"
in a way they don't understand "conscientiousness=0.72, depth_preference=0.81".
The 4 MBTI letters are derived from our continuous dimensions at display time only.

EMA update: alpha=0.10. Profile calibrated after ≥ 5 interactions.
"""
from __future__ import annotations

import re
from typing import Any

# ── Signal extraction ────────────────────────────────────────────────────────

_CANT_PATTERNS = re.compile(
    r"\b(i can'?t|can'?t do|too hard|impossible|i give up|never (get|understand|learn)|"
    r"not smart enough|i'?m (bad|terrible|awful|hopeless) at|don'?t get it|"
    r"bahut mushkil|samajh nahi|nahi aata)\b",
    re.IGNORECASE,
)
_EFFORT_PATTERNS = re.compile(
    r"\b(i tried|let me try|maybe it'?s|i think|could it be|what if|"
    r"i'?ve been (trying|working)|another way|maine try kiya)\b",
    re.IGNORECASE,
)
_FIXED_PATTERNS = re.compile(
    r"\b(i'?m\s+(just\s+)?(bad|not good|terrible|stupid|dumb) at|"
    r"just bad at|"
    r"i can'?t (ever|never)|"
    r"never going to (understand|get|learn)|"
    r"i'?ll never (understand|get|learn)|"
    r"not (cut out|made) for)\b",
    re.IGNORECASE,
)
_WHY_PATTERNS = re.compile(
    r"\bwhy\b|\bhow does\b|\bhow do\b|\bwhat makes\b|\bwhat causes\b|"
    r"\bhow come\b|\bkyun\b|\bkyunki\b|\bkaise kaam",
    re.IGNORECASE,
)
_PROBING_PATTERNS = re.compile(
    r"\b(explain|tell me why|what is the reason|how exactly|prove|show me why|"
    r"break (it|this) down|what'?s behind|underlying|samjhao)\b",
    re.IGNORECASE,
)
_STRUCTURE_PATTERNS = re.compile(
    r"\b(step by step|step-by-step|how to|teach me|show me how|walk me through|"
    r"in order|first.*then|procedure|method|process)\b",
    re.IGNORECASE,
)
_IMPROVEMENT_PATTERNS = re.compile(
    r"\b(how can i (improve|get better|do better)|what did i (do wrong|miss)|"
    r"where did i (go wrong|make a mistake)|practice|revise|aur better kaise)\b",
    re.IGNORECASE,
)
_COMPARISON_PATTERNS = re.compile(
    r"\b(better than|worse than|my (friend|classmate|sister|brother)|"
    r"compared to|others (can|do|get)|everyone else|rank)\b",
    re.IGNORECASE,
)
_HEDGING_PATTERNS = re.compile(
    r"\b(am i right|is this correct|did i get|not sure|i (might|may) be wrong|"
    r"sahi hai kya|theek hai kya)\b",
    re.IGNORECASE,
)

# ── New: Extroversion signals ─────────────────────────────────────────────────
_SOCIAL_PATTERNS = re.compile(
    r"\b(my (friend|classmate|team|group|class)|we (did|learned|were)|"
    r"everyone|together|club|competition|mera dost|hamare class)\b",
    re.IGNORECASE,
)
_ENTHUSIASM_PATTERNS = re.compile(
    r"(!{2,}|\bwow\b|\bomg\b|\byay\b|\bawesome\b|\bso cool\b|\bamazing\b|"
    r"\bwah\b|\bkamaal\b|\bshabash\b)",
    re.IGNORECASE,
)
_REFLECTIVE_PATTERNS = re.compile(
    r"\b(i wonder|thinking about|makes me (think|wonder|realize)|"
    r"i realize|mujhe lagta hai|soch raha tha)\b",
    re.IGNORECASE,
)

# ── New: Thinking vs Feeling signals ─────────────────────────────────────────
_LOGIC_PATTERNS = re.compile(
    r"\b(because|therefore|logically|it follows|proof|disprove|"
    r"makes sense|doesn'?t make sense|mathematically|technically|"
    r"isliye|toh matlab|proof karo)\b",
    re.IGNORECASE,
)
_VALUES_PATTERNS = re.compile(
    r"\b(unfair|it'?s wrong|i feel (like|that)|it bothers me|"
    r"doesn'?t seem right|caring|people|helps (others|people|society)|"
    r"galat hai|ye sahi nahi|mujhe bura lagta)\b",
    re.IGNORECASE,
)


def extract_psyche_signals(
    message: str,
    signals: dict,
    eval_result: dict,
    profile: dict,
) -> dict[str, float]:
    """
    Extract per-interaction psyche signals (all in [0, 1]).
    Returns all 7 dimensions.
    """
    text = message.lower()
    emotion       = eval_result.get("emotion", "neutral")
    emotion_hint  = signals.get("emotion_hint", "neutral")
    engagement    = float(eval_result.get("engagement", 5))
    misconception = bool(eval_result.get("misconception"))
    word_count    = signals.get("word_count", 0)
    streak        = float(profile.get("streak_days") or 0)

    # ── 1. Conscientiousness → MBTI J/P ─────────────────────────────────
    organized     = float(word_count > 12)
    wants_steps   = float(bool(_STRUCTURE_PATTERNS.search(message)))
    streak_score  = min(1.0, streak / 7.0)
    conscientiousness = (
        0.30 * organized +
        0.30 * wants_steps +
        0.40 * streak_score
    )

    # ── 2. Growth Mindset ────────────────────────────────────────────────
    has_effort = float(bool(_EFFORT_PATTERNS.search(message)))
    has_fixed  = float(bool(_FIXED_PATTERNS.search(message)))
    if misconception:
        growth_mindset = (engagement / 10.0) * 0.70 + 0.20 * has_effort - 0.10 * has_fixed
    else:
        growth_mindset = 0.50 + 0.30 * has_effort - 0.40 * has_fixed
    growth_mindset = max(0.0, min(1.0, growth_mindset))

    # ── 3. Anxiety ───────────────────────────────────────────────────────
    has_cant      = float(bool(_CANT_PATTERNS.search(message)))
    hedging_count = len(_HEDGING_PATTERNS.findall(message))
    confused_score   = 1.0 if emotion == "confused" else (0.6 if emotion_hint == "confused" else 0.0)
    disengaged_score = 1.0 if emotion == "disengaged" else 0.0
    anxiety = (
        0.40 * has_cant +
        0.20 * min(1.0, hedging_count / 2.0) +
        0.25 * confused_score +
        0.15 * disengaged_score
    )

    # ── 4. Depth Preference (NFC) → MBTI N/S ────────────────────────────
    has_why     = float(bool(_WHY_PATTERNS.search(message)))
    has_probing = float(bool(_PROBING_PATTERNS.search(message)))
    complex_q   = float(word_count > 18)
    depth_preference = (
        0.35 * has_why +
        0.30 * has_probing +
        0.35 * complex_q
    )

    # ── 5. Mastery Orientation ───────────────────────────────────────────
    has_improvement = float(bool(_IMPROVEMENT_PATTERNS.search(message)))
    has_comparison  = float(bool(_COMPARISON_PATTERNS.search(message)))
    if has_improvement or has_comparison:
        mastery_orientation = 0.70 * has_improvement + 0.30 * (1.0 - has_comparison)
    else:
        mastery_orientation = 0.50

    # ── 6. Extroversion → MBTI E/I ──────────────────────────────────────
    # E signals: social references, enthusiasm, fast/short replies
    # I signals: reflective language, long thoughtful messages
    social_count     = len(_SOCIAL_PATTERNS.findall(message))
    enthusiasm_count = len(_ENTHUSIASM_PATTERNS.findall(message))
    is_reflective    = float(bool(_REFLECTIVE_PATTERNS.search(message)))
    brevity_score    = max(0.0, 1.0 - word_count / 30.0)   # short = E hint
    extroversion = (
        0.35 * min(1.0, social_count / 2.0) +
        0.25 * min(1.0, enthusiasm_count / 2.0) +
        0.25 * brevity_score +
        0.15 * (1.0 - is_reflective)
    )

    # ── 7. Thinking vs Feeling → MBTI T/F ───────────────────────────────
    # T signals: logic/proof language. F signals: values/feelings language.
    logic_count  = len(_LOGIC_PATTERNS.findall(message))
    values_count = len(_VALUES_PATTERNS.findall(message))
    if logic_count == 0 and values_count == 0:
        thinking_feeling = 0.50
    else:
        total = logic_count + values_count
        thinking_feeling = logic_count / total  # → 1 = pure T, 0 = pure F

    return {
        "conscientiousness":   round(max(0.0, min(1.0, conscientiousness)), 3),
        "growth_mindset":      round(max(0.0, min(1.0, growth_mindset)), 3),
        "anxiety":             round(max(0.0, min(1.0, anxiety)), 3),
        "depth_preference":    round(max(0.0, min(1.0, depth_preference)), 3),
        "mastery_orientation": round(max(0.0, min(1.0, mastery_orientation)), 3),
        "extroversion":        round(max(0.0, min(1.0, extroversion)), 3),
        "thinking_feeling":    round(max(0.0, min(1.0, thinking_feeling)), 3),
    }


# ── EMA update ───────────────────────────────────────────────────────────────

EMA_ALPHA = 0.10

_ALL_DIMS = [
    "conscientiousness", "growth_mindset", "anxiety",
    "depth_preference", "mastery_orientation",
    "extroversion", "thinking_feeling",
]


def ema_update(old: float, signal: float) -> float:
    return round((1.0 - EMA_ALPHA) * old + EMA_ALPHA * signal, 4)


# ── Database helpers ─────────────────────────────────────────────────────────

async def get_psyche(conn, learner_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM learner_state.psyche WHERE learner_id = $1",
        learner_id,
    )
    if row:
        d = dict(row)
        # Back-fill new columns for old rows that predate the schema migration
        d.setdefault("extroversion", 0.5)
        d.setdefault("thinking_feeling", 0.5)
        return d
    return {
        "learner_id":          learner_id,
        "conscientiousness":   0.5,
        "growth_mindset":      0.5,
        "anxiety":             0.5,
        "depth_preference":    0.5,
        "mastery_orientation": 0.5,
        "extroversion":        0.5,
        "thinking_feeling":    0.5,
        "sample_count":        0,
    }


async def update_psyche(conn, learner_id: str, signals: dict[str, float]) -> dict:
    current  = await get_psyche(conn, learner_id)
    new_vals = {dim: ema_update(current.get(dim, 0.5), signals[dim])
                for dim in signals if dim in _ALL_DIMS}
    new_count = current["sample_count"] + 1
    await conn.execute(
        """
        INSERT INTO learner_state.psyche
            (learner_id, conscientiousness, growth_mindset, anxiety,
             depth_preference, mastery_orientation, extroversion, thinking_feeling,
             sample_count)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (learner_id) DO UPDATE
        SET conscientiousness   = $2,
            growth_mindset      = $3,
            anxiety             = $4,
            depth_preference    = $5,
            mastery_orientation = $6,
            extroversion        = $7,
            thinking_feeling    = $8,
            sample_count        = $9,
            last_updated        = now()
        """,
        learner_id,
        new_vals.get("conscientiousness",   current.get("conscientiousness", 0.5)),
        new_vals.get("growth_mindset",      current.get("growth_mindset", 0.5)),
        new_vals.get("anxiety",             current.get("anxiety", 0.5)),
        new_vals.get("depth_preference",    current.get("depth_preference", 0.5)),
        new_vals.get("mastery_orientation", current.get("mastery_orientation", 0.5)),
        new_vals.get("extroversion",        current.get("extroversion", 0.5)),
        new_vals.get("thinking_feeling",    current.get("thinking_feeling", 0.5)),
        new_count,
    )
    return {**current, **new_vals, "sample_count": new_count}


# ── MBTI Layer — parent-facing communication vocabulary ──────────────────────

# Maps 4-letter code → (Keirsey name, pedagogy note, famous examples)
_MBTI_TABLE: dict[str, tuple[str, str, list[str]]] = {
    "ISTJ": (
        "The Inspector",
        "Respects authority and procedure. Needs facts first, explicit steps, "
        "and a clear purpose. Dislikes ambiguity. Rewards accuracy over creativity.",
        ["Queen Elizabeth II", "Warren Buffett", "George Washington"],
    ),
    "ISFJ": (
        "The Protector",
        "Loyal, warm, detail-oriented. Connects best through personal caring. "
        "Needs step-by-step and consistent encouragement. Dislikes conflict.",
        ["Mother Teresa", "Rosa Parks", "Kate Middleton"],
    ),
    "INFJ": (
        "The Counselor",
        "Seeks deep meaning and big-picture purpose. Explain WHY something matters "
        "to the world before the mechanics. Responds to ideals and human impact.",
        ["Mahatma Gandhi", "Carl Jung", "Sidney Poitier", "Nelson Mandela"],
    ),
    "INTJ": (
        "The Mastermind",
        "Strategic, independent, efficiency-focused. Needs logical coherence — "
        "skip hand-holding, give the full elegant system. Hates wasted time.",
        ["Isaac Newton", "Stephen Hawking", "Nikola Tesla"],
    ),
    "ISTP": (
        "The Craftsman",
        "Pragmatic hands-on problem solver. Lead with real applications and tools. "
        "Answer 'what does this do?' before 'why does it work?'",
        ["Clint Eastwood", "Bear Grylls", "Amelia Earhart"],
    ),
    "ISFP": (
        "The Composer",
        "Gentle, sensory, lives in the moment. Needs personal relevance and "
        "aesthetics. Give space and calm. Avoid pressure or competition.",
        ["John Keats", "Steven Spielberg", "Michael Jackson", "A.R. Rahman"],
    ),
    "INFP": (
        "The Healer",
        "Deeply values-driven and idealistic. Connect every concept to human "
        "meaning. Authentic personal stories resonate more than abstract rules.",
        ["George Orwell", "J.R.R. Tolkien", "William Shakespeare (often)"],
    ),
    "INTP": (
        "The Architect",
        "Loves logical systems, paradoxes, and first principles. Explain the "
        "deep mechanism, not just the procedure. Welcome their 'but why?' instinct.",
        ["Albert Einstein", "Charles Darwin", "Blaise Pascal"],
    ),
    "ESTP": (
        "The Promoter",
        "Bold, action-first, competitive. Use fast-paced real-world challenges. "
        "Keep it energetic and concrete. Competition and stakes raise engagement.",
        ["Winston Churchill", "John F. Kennedy", "Theodore Roosevelt"],
    ),
    "ESFP": (
        "The Performer",
        "Enthusiastic, social, spontaneous. Learning must be fun and social. "
        "Use stories, drama, games. Variety is essential — avoid long dry explanations.",
        ["Bill Clinton", "Harry Houdini", "Elvis Presley", "Marilyn Monroe"],
    ),
    "ENFP": (
        "The Champion",
        "Loves possibilities, connections, and inspiration. Open with 'imagine if…' "
        "Link every topic to a bigger idea. Needs variety and personal meaning.",
        ["Mark Twain", "Robin Williams", "Walt Disney"],
    ),
    "ENTP": (
        "The Inventor",
        "Clever, loves debate and creative problem-solving. Challenge them with "
        "paradoxes and edge cases. Welcome pushback — they learn through argument.",
        ["Thomas Edison", "Benjamin Franklin", "Socrates"],
    ),
    "ESTJ": (
        "The Supervisor",
        "Values order, efficiency, and traditional structure. Give clear expectations "
        "and measurable milestones. They want to know how they rank.",
        ["Henry Ford", "Lyndon B. Johnson", "Sonia Sotomayor"],
    ),
    "ESFJ": (
        "The Provider",
        "Social harmony and belonging are motivators. Learn through helping others. "
        "Praise and approval matter greatly. Frame learning as serving the community.",
        ["J.C. Penney", "William Howard Taft", "Mary Wollstonecraft"],
    ),
    "ENFJ": (
        "The Teacher",
        "Natural leader who learns by teaching others. Connect topics to people "
        "and social impact. Responds to inspiration and group purpose.",
        ["Martin Luther King Jr.", "Barack Obama", "Oprah Winfrey"],
    ),
    "ENTJ": (
        "The Field Marshal",
        "Strategic commander. Needs big-picture frameworks and clear efficiency. "
        "Give the system, then the details. Challenges should feel like campaigns.",
        ["Napoleon Bonaparte", "Steve Jobs", "Julius Caesar"],
    ),
}


def compute_mbti(psyche: dict, min_samples: int = 15) -> dict:
    """
    Derive a 4-letter MBTI type from continuous psyche dimensions.
    Returns None type if insufficient data.

    E/I  ← extroversion    (>0.5 = E)
    N/S  ← depth_preference (>0.5 = N, conceptual; ≤0.5 = S, concrete)
    T/F  ← thinking_feeling (>0.5 = T; ≤0.5 = F)
    J/P  ← conscientiousness (>0.5 = J; ≤0.5 = P)
    """
    sample_count = psyche.get("sample_count", 0)
    if sample_count < min_samples:
        return {
            "type": None,
            "name": None,
            "note": f"Needs {min_samples - sample_count} more interactions to estimate type.",
            "confidence": "low",
            "examples": [],
            "pedagogy": None,
        }

    e = "E" if psyche.get("extroversion",     0.5) > 0.5 else "I"
    n = "N" if psyche.get("depth_preference", 0.5) > 0.5 else "S"
    t = "T" if psyche.get("thinking_feeling", 0.5) > 0.5 else "F"
    j = "J" if psyche.get("conscientiousness",0.5) > 0.5 else "P"
    code = e + n + t + j

    name, pedagogy, examples = _MBTI_TABLE[code]

    # Confidence: higher if dimensions are far from 0.5
    dims = [
        abs(psyche.get("extroversion",     0.5) - 0.5),
        abs(psyche.get("depth_preference", 0.5) - 0.5),
        abs(psyche.get("thinking_feeling", 0.5) - 0.5),
        abs(psyche.get("conscientiousness",0.5) - 0.5),
    ]
    avg_clarity = sum(dims) / len(dims)
    confidence = "high" if avg_clarity > 0.18 else ("moderate" if avg_clarity > 0.09 else "low")

    return {
        "type":       code,
        "name":       name,
        "confidence": confidence,
        "examples":   examples,
        "pedagogy":   pedagogy,
        "note": (
            f"Estimated from {sample_count} interactions. "
            "This is an inference, not a clinical assessment."
        ),
        "dimensions_used": {
            "E_vs_I": f"{psyche.get('extroversion', 0.5):.2f} → {e}",
            "N_vs_S": f"{psyche.get('depth_preference', 0.5):.2f} → {n}",
            "T_vs_F": f"{psyche.get('thinking_feeling', 0.5):.2f} → {t}",
            "J_vs_P": f"{psyche.get('conscientiousness', 0.5):.2f} → {j}",
        },
    }


# ── Pedagogical prompt injection ──────────────────────────────────────────────

_RULES = [
    # Conscientiousness
    ("conscientiousness", "low", 0.35,
     "Provide explicit scaffolding: state the goal upfront ('We'll learn X in 3 steps'), "
     "number every step, confirm completion before moving on."),
    ("conscientiousness", "high", 0.65,
     "State the objective first, give a structured explanation, then summarise. "
     "They respond well to checklists and explicit progress markers."),

    # Anxiety — Hembree (1990)
    ("anxiety", "high", 0.60,
     "IMPORTANT: Learning anxiety detected. NEVER use 'wrong', 'incorrect', 'mistake'. "
     "Say 'let's look from another angle'. Celebrate every micro-step. "
     "Use shorter sentences. Check in frequently with gentle prompts."),
    ("anxiety", "low", 0.25,
     "Confident learner — introduce productive challenge: "
     "'Here's a trickier version — what do you think?'"),

    # Growth Mindset — Yeager et al. (2019)
    ("growth_mindset", "low", 0.35,
     "IMPORTANT: Fixed mindset signals. NEVER say 'you're smart' or 'you're not a maths person'. "
     "Attribute outcomes to effort: 'Trying three methods is exactly how the brain gets stronger.' "
     "When they fail, say 'not yet'."),
    ("growth_mindset", "high", 0.65,
     "Growth-oriented — reinforce process: 'What strategy are you using here?' "
     "Challenge slightly beyond comfort zone."),

    # Depth Preference
    ("depth_preference", "high", 0.65,
     "Conceptual thinker. Explain WHY before the rule. Use 'here's what's really happening "
     "underneath' — they find principles more satisfying than procedures."),
    ("depth_preference", "low", 0.30,
     "Procedural preference. Lead with worked example, then name the rule. "
     "Skip proofs. Keep explanations concrete."),

    # Mastery Orientation
    ("mastery_orientation", "high", 0.65,
     "Improvement-focused. Reference their own past: "
     "'Remember when fractions felt hard? Look at you now.' "
     "Avoid any comparison to other students."),
    ("mastery_orientation", "low", 0.35,
     "May be externally motivated. Connect to real-world outcomes they care about."),

    # Extroversion — new
    ("extroversion", "high", 0.65,
     "Extroverted learner — use energetic tone, group analogies, "
     "'imagine you're explaining this to your friend…' "
     "Short punchy exchanges work better than long explanations."),
    ("extroversion", "low", 0.35,
     "Introverted learner — give space to think before responding. "
     "Ask one question at a time. Long reflective explanations are welcome."),

    # Thinking vs Feeling — new
    ("thinking_feeling", "high", 0.65,
     "Thinking-type learner. Lead with logic, proof, and precise definitions. "
     "They respond to 'here's why this must be true' over 'here's how to feel about it'."),
    ("thinking_feeling", "low", 0.35,
     "Feeling-type learner. Connect concepts to human stories and real-world impact. "
     "Lead with 'here's why this matters to people' before the mechanics."),
]

MIN_SAMPLES_FOR_CALIBRATION = 5


def build_psyche_instructions(psyche: dict) -> str:
    if psyche.get("sample_count", 0) < MIN_SAMPLES_FOR_CALIBRATION:
        return ""

    instructions = []
    for dim, direction, threshold, text in _RULES:
        val = psyche.get(dim, 0.5)
        if direction == "high" and val >= threshold:
            instructions.append(f"- {text}")
        elif direction == "low" and val <= threshold:
            instructions.append(f"- {text}")

    if not instructions:
        return ""

    return (
        "\n\nPedagogical calibration (inferred from this child's patterns):\n"
        + "\n".join(instructions)
    )


# ── Human-readable interpretation ────────────────────────────────────────────

_DIMENSION_META = {
    "conscientiousness": {
        "name":  "Conscientiousness (→ J/P)",
        "basis": "Big Five — Poropat (2009)",
        "low":   "Needs scaffolding and explicit structure (MBTI: P — flexible/spontaneous)",
        "mid":   "Moderately organised",
        "high":  "Self-directed, goal-oriented (MBTI: J — structured, planned)",
    },
    "anxiety": {
        "name":  "Learning Anxiety",
        "basis": "Big Five Neuroticism — Hembree (1990)",
        "low":   "Confident, handles challenge well",
        "mid":   "Moderate anxiety",
        "high":  "Anxiety signals — needs error-safe language and micro-confirmations",
    },
    "growth_mindset": {
        "name":  "Growth Mindset",
        "basis": "Dweck / Yeager et al. (N=12,490)",
        "low":   "Fixed mindset — avoid ability praise, use 'not yet'",
        "mid":   "Mixed orientation",
        "high":  "Growth-oriented — reinforce process, introduce challenge",
    },
    "depth_preference": {
        "name":  "Depth Preference (→ N/S)",
        "basis": "Need for Cognition — Richardson et al.",
        "low":   "Concrete procedural preference (MBTI: S — sensing, practical)",
        "mid":   "Balanced",
        "high":  "Conceptual thinker (MBTI: N — intuitive, loves patterns)",
    },
    "mastery_orientation": {
        "name":  "Mastery Orientation",
        "basis": "Achievement Goal Theory — Elliot & McGregor (2001)",
        "low":   "Extrinsic motivation — connect to tangible outcomes",
        "mid":   "Mixed motivation",
        "high":  "Improvement-focused — use self-referenced progress",
    },
    "extroversion": {
        "name":  "Extroversion (→ E/I)",
        "basis": "Big Five — DeYoung (2015)",
        "low":   "Introverted — reflective, needs space, prefers depth (MBTI: I)",
        "mid":   "Ambivert",
        "high":  "Extroverted — social, enthusiastic, energised by interaction (MBTI: E)",
    },
    "thinking_feeling": {
        "name":  "Thinking vs Feeling (→ T/F)",
        "basis": "Big Five Agreeableness inverse",
        "low":   "Values/feeling orientation — connect to human impact (MBTI: F)",
        "mid":   "Balanced logic and values",
        "high":  "Logic/thinking orientation — lead with proof and reason (MBTI: T)",
    },
}


def interpret_psyche(psyche: dict) -> dict:
    """Return a human-readable profile for the /psyche API and parent dashboard."""
    sample_count = psyche.get("sample_count", 0)
    confident = sample_count >= MIN_SAMPLES_FOR_CALIBRATION

    dimensions = {}
    for dim, meta in _DIMENSION_META.items():
        val = psyche.get(dim, 0.5)
        if val >= 0.65:
            level, description = "high", meta["high"]
        elif val <= 0.35:
            level, description = "low", meta["low"]
        else:
            level, description = "moderate", meta["mid"]
        dimensions[dim] = {
            "score":       val,
            "level":       level,
            "name":        meta["name"],
            "evidence":    meta["basis"],
            "description": description,
        }

    active_rules = []
    for dim, direction, threshold, text in _RULES:
        val = psyche.get(dim, 0.5)
        if (direction == "high" and val >= threshold) or (direction == "low" and val <= threshold):
            active_rules.append({"dimension": dim, "direction": direction, "instruction": text})

    mbti = compute_mbti(psyche)

    return {
        "sample_count":  sample_count,
        "confident":     confident,
        "note": (
            "Profile has sufficient data for calibration."
            if confident else
            f"Needs {MIN_SAMPLES_FOR_CALIBRATION - sample_count} more interactions."
        ),
        "mbti":                     mbti,
        "dimensions":               dimensions,
        "active_pedagogical_rules": active_rules if confident else [],
    }
