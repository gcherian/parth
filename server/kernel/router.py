"""
Routing table — maps event types to ordered module execution plans.
Parallel([...]) runs modules concurrently.
Sequential([...]) runs modules one after another.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger

log = get_logger("kernel.router")


@dataclass
class Parallel:
    module_names: list[str]


@dataclass
class Sequential:
    module_names: list[str]


# The routing table is the kernel's only knowledge of modules.
#
# All steps are Sequential: modules share a single asyncpg connection (ctx.db),
# and asyncpg does not support concurrent queries on the same connection.
# The Ollama LLM call (tutor.runtime) dominates latency, so sequential
# pre/post phases add negligible overhead.
ROUTING_TABLE: dict[str, list[Parallel | Sequential]] = {
    "interaction.requested": [
        Sequential(["moderation.ops", "learner.state", "curriculum.graph"]),
        Sequential(["tutor.runtime"]),
        Sequential(["moderation.ops", "learner.state", "practice.engine"]),
    ],
    "practice.session_requested": [
        Sequential(["learner.state", "curriculum.graph", "practice.engine"]),
    ],
    "parent.report_requested": [
        Sequential(["learner.state", "parent.dashboard"]),
    ],
}


class Router:
    def __init__(self, modules: dict[str, Module]):
        self._modules = modules

    async def execute(
        self, event_type: str, event: Event, ctx: KernelContext
    ) -> KernelContext:
        steps = ROUTING_TABLE.get(event_type, [])
        for step in steps:
            if isinstance(step, Parallel):
                await self._run_parallel(step.module_names, event, ctx)
            else:
                await self._run_sequential(step.module_names, event, ctx)
            # Veto from moderation.ops short-circuits the entire pipeline
            if not ctx.moderation_ok:
                log.info("pipeline_vetoed", request_id=ctx.request_id)
                break
        return ctx

    async def _run_parallel(
        self, names: list[str], event: Event, ctx: KernelContext
    ):
        tasks = [self._call(name, event, ctx) for name in names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                log.error("module_exception", module=name, error=str(result))
            elif isinstance(result, ModuleResult):
                self._merge(name, result, ctx)

    async def _run_sequential(
        self, names: list[str], event: Event, ctx: KernelContext
    ):
        for name in names:
            result = await self._call(name, event, ctx)
            if isinstance(result, Exception):
                log.error("module_exception", module=name, error=str(result))
            else:
                self._merge(name, result, ctx)
            if not ctx.moderation_ok:
                break

    async def _call(self, name: str, event: Event, ctx: KernelContext) -> ModuleResult:
        module = self._modules.get(name)
        if module is None:
            log.warning("module_not_found", module=name)
            return ModuleResult(success=False, error=f"module {name!r} not registered")
        try:
            log.debug("module_call", module=name, request_id=ctx.request_id)
            return await module.handle(event, ctx)
        except Exception as e:
            log.error("module_error", module=name, error=str(e))
            return ModuleResult(success=False, error=str(e))

    def _merge(self, name: str, result: ModuleResult, ctx: KernelContext):
        if result.veto:
            ctx.moderation_ok = False
            ctx.response_text = result.veto_response
        ctx.module_data[name] = result.data
        # Pull well-known fields out of module_data into first-class ctx fields
        if "learner_context" in result.data:
            ctx.learner_context = result.data["learner_context"]
        if "curriculum_context" in result.data:
            ctx.curriculum_context = result.data["curriculum_context"]
        if "response_text" in result.data:
            ctx.response_text = result.data["response_text"]
        if "model_used" in result.data:
            ctx.model_used = result.data["model_used"]
        if "distress_detected" in result.data:
            ctx.distress_detected = result.data["distress_detected"]
