from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSignals:
    learner_id: str
    session_id: str
    phase: str                       # 'pre' | 'post'
    message: str = ""
    response_text: str = ""
    subject: str = "General"
    grade: int = 6
    concepts: list[str] = field(default_factory=list)
    emotion: str = "neutral"
    engagement: float = 5.0
    misconception: str = ""
    misconception_concept: str = ""
    language_ratio: float = 1.0
    total_questions: int = 0
    prev_domains: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)
    eval_result: dict = field(default_factory=dict)
    elapsed_ms: int = 0   # time taken to answer (for SAINT+ temporal features)
    lag_ms: int = 0       # gap since last interaction (for SAINT+ temporal features)
    events: dict[str, Any] = field(default_factory=dict)  # inter-agent event bus


class LearnerAgent(ABC):
    name: str
    phase: str = "post"
    memory_window: str = "permanent"

    @abstractmethod
    async def observe(self, signals: AgentSignals, conn) -> None: ...

    @abstractmethod
    async def read(self, conn, learner_id: str) -> str: ...

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}
