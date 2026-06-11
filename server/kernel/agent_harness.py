import asyncio
from foundation.observability import get_logger
from kernel.agent import LearnerAgent, AgentSignals

log = get_logger("kernel.agent_harness")


class AgentHarness:
    def __init__(self, agents: list[LearnerAgent]):
        self._agents = agents

    async def build_context(self, conn, learner_id: str) -> str:
        # Run all agent.read() in parallel, join non-empty with double newline
        reads = await asyncio.gather(
            *[a.read(conn, learner_id) for a in self._agents],
            return_exceptions=True,
        )
        parts = []
        for agent, result in zip(self._agents, reads):
            if isinstance(result, Exception):
                log.warning("agent_read_failed", agent=agent.name, error=str(result))
            elif result:
                parts.append(result)
        return "\n\n".join(parts)

    async def dispatch(self, signals: AgentSignals, conn) -> None:
        # Run agents in dependency order, collect inter-agent events
        for agent in self._agents:
            if agent.phase not in ("post", "both"):
                continue
            try:
                await agent.observe(signals, conn)
                signals.events.update(agent.emit(signals))
            except Exception as e:
                log.warning("agent_observe_failed", agent=agent.name, error=str(e))
