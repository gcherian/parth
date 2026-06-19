import asyncio
from foundation.observability import get_logger
from kernel.agent import LearnerAgent, AgentSignals

log = get_logger("kernel.agent_harness")


class AgentHarness:
    def __init__(self, agents: list[LearnerAgent]):
        self._agents = agents

    async def build_context(self, conn, learner_id: str) -> str:
        """Join all agent read() outputs into a single context string."""
        context, _ = await self.build_context_traced(conn, learner_id)
        return context

    async def build_context_traced(
        self, conn, learner_id: str
    ) -> tuple[str, list[dict]]:
        """
        Run all agent read() sequentially (shared asyncpg connection cannot handle
        concurrent queries) and return (context_str, per-agent read trace).
        """
        parts: list[str] = []
        read_trace: list[dict] = []
        for agent in self._agents:
            try:
                result = await agent.read(conn, learner_id)
                read_trace.append({"agent": agent.name, "read": result or "", "error": None})
                if result:
                    parts.append(result)
            except Exception as e:
                log.warning("agent_read_failed", agent=agent.name, error=str(e))
                read_trace.append({"agent": agent.name, "read": "", "error": str(e)})
        return "\n\n".join(parts), read_trace

    async def dispatch(
        self, signals: AgentSignals, conn
    ) -> list[dict]:
        """
        Run agents in dependency order.

        Each agent may:
          observe() — write to DB / update signals
          emit()    — publish events onto signals.events (read by downstream agents)

        Returns a dispatch trace: one dict per agent showing what it emitted
        and the full event-bus snapshot after it ran.
        """
        dispatch_trace: list[dict] = []
        for agent in self._agents:
            if agent.phase not in ("post", "both"):
                dispatch_trace.append({
                    "agent": agent.name, "skipped": True,
                    "emitted": {}, "events_snapshot": dict(signals.events),
                })
                continue
            events_before = dict(signals.events)
            error = None
            emitted: dict = {}
            try:
                await agent.observe(signals, conn)
                emitted = agent.emit(signals)
                signals.events.update(emitted)
            except Exception as e:
                error = str(e)
                log.warning("agent_observe_failed", agent=agent.name, error=error)

            dispatch_trace.append({
                "agent":           agent.name,
                "skipped":         False,
                "emitted":         emitted,
                "events_before":   events_before,
                "events_snapshot": dict(signals.events),
                "error":           error,
            })
        return dispatch_trace
