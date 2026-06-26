"""
Learner Agent interfaces — the plug-in contract for the 15-agent harness.

LearnerAgent: abstract interface (ABC)
BaseAgent:    resilient implementation base — wraps _observe() / _read() with
              structured error logging so agent failures never silently corrupt
              the learner model.

Agent authors override _observe() and _read() only; observe() and read()
are owned by BaseAgent and must not be overridden.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from foundation.observability import get_logger

log = get_logger("kernel.agent")


@dataclass
class AgentSignals:
    """
    Shared signal bus passed to every agent in the dispatch loop.

    Pre-generation signals come from heuristic extraction (signals.py).
    Post-generation signals are enriched by the LLM evaluator and the
    event bus (signals.events) which agents write to via emit().
    """
    learner_id: str
    session_id: str
    phase: str                        # 'pre' | 'post'
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
    elapsed_ms: int = 0               # time taken to answer (SAINT+ temporal feature)
    lag_ms: int = 0                   # gap since last interaction (SAINT+ temporal feature)
    events: dict[str, Any] = field(default_factory=dict)  # inter-agent event bus


class LearnerAgent(ABC):
    """
    Abstract interface for all learner agents.

    Kernel contract:
      • observe() — post-generation: write learner state to DB
      • emit()    — post-generation: publish events onto the shared bus
      • read()    — pre-generation:  return a context string injected into the LLM prompt

    Active agents extend BaseAgent (below), which adds error handling.
    Legacy / experimental agents may extend LearnerAgent directly.
    """
    name: str
    phase: str = "post"
    memory_window: str = "permanent"

    @abstractmethod
    async def observe(self, signals: AgentSignals, conn) -> None: ...

    @abstractmethod
    async def read(self, conn, learner_id: str) -> str: ...

    def emit(self, signals: AgentSignals) -> dict[str, Any]:
        return {}


class BaseAgent(LearnerAgent):
    """
    Resilient base for all 15 registered agents in the learner harness.

    Implements the observe / read contract with:
      • Structured warning logs on any failure (never silent)
      • Safe fallbacks: observe is a no-op; read returns ""

    Agents override _observe() and _read() — their implementations contain
    pure domain logic with no error-handling boilerplate.
    """

    async def observe(self, signals: AgentSignals, conn) -> None:
        try:
            await self._observe(signals, conn)
        except Exception as exc:
            log.warning(
                "agent_observe_failed",
                agent=self.name,
                learner_id=signals.learner_id,
                error=str(exc),
            )

    async def read(self, conn, learner_id: str) -> str:
        try:
            return await self._read(conn, learner_id) or ""
        except Exception as exc:
            log.warning(
                "agent_read_failed",
                agent=self.name,
                learner_id=learner_id,
                error=str(exc),
            )
            return ""

    async def get_config(self, conn, learner_id: str) -> dict:
        """Return per-child config for this agent merged with schema defaults.

        Lazy import avoids circular dependency at module load time.
        Falls back to schema defaults if tables don't exist yet.
        """
        from modules.learner_state.child_config import load as _load_child_config
        cfg = await _load_child_config(conn, learner_id)
        return cfg.agent(self.name)

    @abstractmethod
    async def _observe(self, signals: AgentSignals, conn) -> None: ...

    @abstractmethod
    async def _read(self, conn, learner_id: str) -> str: ...
