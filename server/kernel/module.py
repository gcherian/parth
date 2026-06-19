from abc import ABC, abstractmethod

from kernel.context import Event, KernelContext, ModuleResult


class Module(ABC):
    name: str = ""
    handles: list[str] = []

    @abstractmethod
    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        """
        Called by the kernel inside the active Postgres transaction.
        Must be idempotent on event.request_id.
        Return ModuleResult; raise only for truly unexpected errors.
        """

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        """Right-to-erasure hook — delete all PII for this learner."""
