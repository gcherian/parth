"""
L2 Microkernel — Tutor Orchestrator.

Stateless · Transactional · Idempotent · Event-routing only.

The kernel knows nothing about curriculum, learner psychology, or LLMs.
It only:
  1. Checks idempotency
  2. Opens a Postgres transaction
  3. Routes events to modules
  4. Commits the transaction + outbox row
  5. Returns the response
"""
from __future__ import annotations

import json
import time
import uuid

from foundation.db import get_pool
from foundation.outbox import publish
from foundation.observability import get_logger, set_request_context
from kernel.context import Event, KernelContext, ModuleResult
from kernel.router import Router

log = get_logger("kernel.orchestrator")


class Orchestrator:
    def __init__(self, router: Router):
        self._router = router

    async def handle(
        self,
        learner_id: str,
        message: str,
        subject: str,
        grade: int,
        history: list[dict],
        model_override: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        t0 = time.time()
        request_id = request_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        set_request_context(request_id, trace_id)
        log.info("kernel_request", learner_id=learner_id, subject=subject, grade=grade)

        pool = await get_pool()

        # ── Step 1: Idempotency check ──────────────────────────────────────
        async with pool.acquire() as conn:
            cached = await conn.fetchrow(
                "SELECT response FROM foundation.idempotency WHERE request_id = $1",
                uuid.UUID(request_id),
            )
            if cached:
                log.info("idempotency_hit", request_id=request_id)
                return json.loads(cached["response"])

        # ── Step 2: Build event + context ──────────────────────────────────
        event = Event(
            type="interaction.requested",
            aggregate="learner",
            aggregate_id=learner_id,
            payload={
                "message": message,
                "subject": subject,
                "grade": grade,
                "model_override": model_override,
            },
            request_id=request_id,
            trace_id=trace_id,
        )

        ctx = KernelContext(
            request_id=request_id,
            trace_id=trace_id,
            learner_id=learner_id,
            subject=subject,
            grade=grade,
            message=message,
            history=history,
        )

        # ── Step 3: Transactional execution ───────────────────────────────
        async with pool.acquire() as conn:
            async with conn.transaction():
                ctx.db = conn

                # Publish interaction.requested into outbox (inside transaction)
                await publish(
                    conn, "interaction.requested",
                    {"learner_id": learner_id, "subject": subject, "grade": grade},
                    aggregate="learner", aggregate_id=learner_id,
                )

                # Route through all module phases
                ctx = await self._router.execute("interaction.requested", event, ctx)

                duration_ms = int((time.time() - t0) * 1000)
                response_text = ctx.response_text or "I'm thinking… please try again."
                model_used = ctx.model_used or "unknown"

                ls = ctx.module_data.get("learner.state", {})
                result_payload = {
                    "response": response_text,
                    "model": model_used,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                    "distress_detected": ctx.distress_detected,
                    # monitor-facing signals (not in ChatResponse schema)
                    "_emotion":      ls.get("emotion", "neutral"),
                    "_engagement":   ls.get("engagement", 5.0),
                    "_misconception": ls.get("misconception", ""),
                }

                # Publish interaction.completed
                await publish(
                    conn, "interaction.completed",
                    {**result_payload, "learner_id": learner_id},
                    aggregate="learner", aggregate_id=learner_id,
                )

                # Write idempotency record (inside same transaction)
                await conn.execute(
                    """
                    INSERT INTO foundation.idempotency (request_id, response)
                    VALUES ($1, $2)
                    ON CONFLICT (request_id) DO NOTHING
                    """,
                    uuid.UUID(request_id), json.dumps(result_payload),
                )

        log.info(
            "kernel_response",
            model=model_used,
            duration_ms=duration_ms,
            moderation_ok=ctx.moderation_ok,
        )
        return result_payload

    async def erase_learner(self, learner_id: str):
        """Cascade right-to-erasure across all registered modules."""
        pool = await get_pool()
        ctx = KernelContext(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            learner_id=learner_id,
            subject="", grade=0, message="",
        )
        async with pool.acquire() as conn:
            ctx.db = conn
            for module in self._router._modules.values():
                try:
                    await module.on_erase(learner_id, ctx)
                except Exception as e:
                    log.error("erase_module_error", module=module.name, error=str(e))
        log.info("learner_erased", learner_id=learner_id)
