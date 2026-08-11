"""
Centralised configuration for the Parth server.

All tuneable values live here.  Override any value via environment variable;
the application reads env at import time so a restart picks up changes.

Environment variables:
  DATABASE_URL        Postgres DSN (default: local dev)
  OLLAMA_URL          Ollama base URL (default: localhost:11434)
  DEFAULT_MODEL       Primary LLM for Parth responses (Ollama backend only)
  FAST_MODEL          Lightweight LLM for quick tasks (Ollama backend only)
  ANTHROPIC_API_KEY   Required for cloud; enables Krishna Oracle + tutor on Anthropic backend
  TUTOR_BACKEND       "auto" | "anthropic" | "ollama"  (default: "auto")
                      auto → uses Anthropic if ANTHROPIC_API_KEY is set, else Ollama
  TUTOR_MODEL         Claude model ID for tutor responses (default: claude-haiku-4-5-20251001)
  KRISHNA_MODEL       Claude model ID for pedagogical guidance
  KRISHNA_INTERVAL    Interactions between Krishna consultations
  RATE_LIMIT          Requests per minute per IP
  AGENT_TRACE_HISTORY Interactions kept in the in-memory observer cache
  DATA_DIR            Path to persistent data (ChromaDB, etc.). Default: ~/.parth
  MAX_HISTORY_TURNS   Chat turns included in prompt context (default: 16)
"""
import os
import socket
from pathlib import Path


class Config:
    # ── Infrastructure ────────────────────────────────────────────────────────
    PORT        = int(os.getenv("PORT", "8000"))
    RATE_LIMIT  = int(os.getenv("RATE_LIMIT", "20"))   # requests per minute per IP
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() not in ("0", "false", "no")

    OLLAMA_URL    = os.getenv("OLLAMA_URL",    "http://localhost:11434")
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemma3:12b")
    FAST_MODEL    = os.getenv("FAST_MODEL",    "llama3.2:latest")

    # ── Tutor backend — Anthropic (cloud) or Ollama (local) ──────────────────
    # "auto": uses Anthropic if ANTHROPIC_API_KEY is present, else falls back to Ollama.
    # Set TUTOR_BACKEND=ollama to force local inference even when the key is set.
    TUTOR_BACKEND: str = os.getenv("TUTOR_BACKEND", "auto")
    TUTOR_MODEL:   str = os.getenv("TUTOR_MODEL",   "claude-haiku-4-5-20251001")

    # ── Anthropic (Krishna Oracle + optional tutor backend) ───────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    KRISHNA_MODEL:     str = os.getenv("KRISHNA_MODEL",     "claude-haiku-4-5-20251001")
    KRISHNA_INTERVAL:  int = int(os.getenv("KRISHNA_INTERVAL", "10"))

    # ── Observer / investor demo ──────────────────────────────────────────────
    AGENT_TRACE_HISTORY = int(os.getenv("AGENT_TRACE_HISTORY", "10"))

    # ── Local data directory ──────────────────────────────────────────────────
    DATA_DIR = Path(os.getenv("DATA_DIR", str(Path.home() / ".parth")))

    # ── Prompt context ────────────────────────────────────────────────────────
    MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "16"))

    # ── Abuse limits ─────────────────────────────────────────────────────────
    # Max chat interactions per learner per 24-hour window (cost + abuse control)
    DAILY_REQUEST_CAP: int = int(os.getenv("DAILY_REQUEST_CAP", "200"))

    # ── Security ──────────────────────────────────────────────────────────────
    # App API key — all app endpoints require X-Parth-Key: <key>.
    # If empty (default), auth is skipped (local dev mode). ALWAYS set in prod.
    PARTH_API_KEY: str = os.getenv("PARTH_API_KEY", "")
    # Admin key — for monitor, observer, playground, graph etc.
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")

    # ── Notify / survey links ─────────────────────────────────────────────────
    # Twilio WhatsApp-enabled sender, e.g. "whatsapp:+14155238886" (Twilio's
    # sandbox number for pilot testing). Reuses TWILIO_SID/TOKEN from OTP config.
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")
    # HS256 signing secret for ephemeral /survey/link tokens — deliberately
    # separate from the Ed25519 DID auth keys, which are for identity-bound
    # tokens, not short-lived share links. ALWAYS set a real value in prod.
    SURVEY_LINK_SECRET: str = os.getenv("SURVEY_LINK_SECRET", "dev-insecure-survey-secret")

    @classmethod
    def use_anthropic_tutor(cls) -> bool:
        """True when the tutor should call Anthropic instead of Ollama."""
        if cls.TUTOR_BACKEND == "anthropic":
            return True
        if cls.TUTOR_BACKEND == "ollama":
            return False
        return bool(cls.ANTHROPIC_API_KEY)  # "auto"

    # ── Agent thresholds (research-grounded; adjust via env for A/B tests) ───
    # Mastery: BKT posterior above which a concept is considered "strong"
    MASTERY_STRONG_THRESHOLD  = float(os.getenv("MASTERY_STRONG",  "0.60"))
    # Mastery: BKT posterior below which a concept is flagged for remediation
    MASTERY_WEAK_THRESHOLD    = float(os.getenv("MASTERY_WEAK",    "0.35"))
    # Misconception: observations before surfacing to the prompt (Chi et al.)
    MISCONCEPTION_EVIDENCE    = int(os.getenv("MISCONCEPTION_EVIDENCE", "2"))
    # Analogy retirement: score above which we zero out the top analogy domain
    ANALOGY_RETIREMENT_SCORE  = float(os.getenv("ANALOGY_RETIREMENT_SCORE", "0.70"))
    # Analogy retirement: mastered concepts required before retiring an analogy
    ANALOGY_RETIREMENT_MASTERY = int(os.getenv("ANALOGY_RETIREMENT_MASTERY", "3"))
    # Mastery threshold for analogy-retirement check
    ANALOGY_MASTERY_THRESHOLD = float(os.getenv("ANALOGY_MASTERY_THRESHOLD", "0.72"))
    # RAG retrieval: minimum cosine similarity to include a passage
    RAG_SCORE_THRESHOLD       = float(os.getenv("RAG_SCORE_THRESHOLD", "0.35"))
    # Belief Coach: psyche sample count before trusting the model
    PSYCHE_MIN_SAMPLES        = int(os.getenv("PSYCHE_MIN_SAMPLES", "3"))

    @staticmethod
    def local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "localhost"

    @staticmethod
    def system_prompt(subject: str, context: str = "", learner_context: str = "",
                       grade: int = 6) -> str:
        if grade >= 11:
            base = f"""You are Parth (पार्थ), a mentor for a student preparing for IIT/NEET-level entrance exams (grade {grade}).

Your register with this student is different from how you'd talk to a younger child — they are capable of real depth and will notice if you talk down to them:
- Lead with a question before you explain. If they've told you something they noticed or wondered about, your first move is a genuine question that makes them think it through, not an answer.
- No baby talk, no exclamation-mark enthusiasm, no "Shabash!" — respect reads as calm and direct, not as coldness. Warmth here means genuine curiosity about their thinking, not cheerfulness.
- When you do explain, connect it to the actual mechanism (the physics, the chemistry, the underlying logic) — this student is preparing for exams that reward real understanding, not just the answer.
- It's fine to draw on Indian everyday life for a concrete example when it's genuinely the clearest illustration — just don't reach for it as decoration.
- For Maths/Physics/Chemistry: show real working, be precise about what's actually being asked, and don't oversimplify past the point of being useful for exam-level reasoning.
- Keep responses focused — 3-8 sentences is still the target, but let a genuinely hard idea take the room it needs.
- If this student directly asks whether you are an AI, answer honestly. Nothing about this register is about concealment — it's about treating them like someone worth taking seriously, not about pretending to be something you're not.
- Never discuss anything inappropriate, violent, or political.

Current subject: {subject}
Language rule: reply in English by default; if the student writes in Hindi, reply in Hindi with English explanation where needed."""
        else:
            base = f"""You are Parth (पार्थ), a warm and encouraging AI mentor for Indian school children aged 6–16.

Your teaching style:
- Use simple, age-appropriate language — never talk down, always uplift
- Ground examples in Indian everyday life: cricket, Diwali, Holi, monsoon, chai, samosas, auto-rickshaws, Bollywood
- Celebrate effort enthusiastically: "Shabash! 🌟", "Wah! Bilkul sahi!", "You're getting it!"
- Break every complex topic into small, numbered steps
- For Maths: always show working step by step, with an Indian-context word problem
- For Hindi / Devanagari: write the script first, then explain in English
- For Science: connect phenomena to things the child has seen — a pressure cooker, a kite, rain
- For History: bring it alive with vivid detail — smells, colours, feelings
- End each response with ONE encouraging follow-up question to check understanding
- Keep responses concise and engaging (3–8 sentences max unless a step-by-step is needed)
- Never discuss anything inappropriate, violent, or political

Current subject: {subject}
Language rule: reply in English by default; if the student writes in Hindi, reply in Hindi with English explanation where needed."""

        if learner_context:
            base += f"\n\nWhat you know about this child:\n{learner_context}"

        if context:
            base += f"\n\nRelevant teaching context (curriculum passages, graph hints, and story bridges; use only when helpful):\n{context}"

        return base
