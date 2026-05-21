import os
import socket
from pathlib import Path


class Config:
    OLLAMA_URL = "http://localhost:11434"
    DEFAULT_MODEL = "gemma3:12b"
    FAST_MODEL = "llama3.2:latest"
    PORT = 8000
    RATE_LIMIT = 20  # requests per minute per IP

    # Krishna Oracle — Anthropic frontier model for background pedagogical guidance
    # Set ANTHROPIC_API_KEY in environment or .env to enable.
    # If absent, Krishna is silently disabled (Parth still works normally).
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    KRISHNA_MODEL: str = "claude-haiku-4-5-20251001"   # cheapest capable frontier model
    KRISHNA_INTERVAL: int = 10                          # interactions between Krishna consultations

    # Data lives on local SSD — never on an external drive that can be unmounted
    DATA_DIR = Path.home() / ".parth"

    @staticmethod
    def local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    @staticmethod
    def system_prompt(subject: str, context: str = "", learner_context: str = "") -> str:
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
            base += f"\n\nRelevant NCERT curriculum content (use this to ground your answer):\n{context}"

        return base
