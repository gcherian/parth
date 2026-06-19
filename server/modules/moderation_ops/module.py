"""
moderation.ops — Content safety with veto power.

Runs twice per interaction:
  Phase 1 (pre-generation): checks the child's input message.
  Phase 3 (post-generation): checks Parth's response.

This is the only module that can abort a kernel transaction unilaterally
by returning ModuleResult(veto=True).
"""
import re

from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger

log = get_logger("moderation.ops")

# Distress signals — conservative: err on the side of flagging
_DISTRESS_PATTERNS = [
    r"\bhurt\s+my\s*self\b",
    r"\bkill\s+my\s*self\b",
    r"\bwant\s+to\s+die\b",
    r"\bsuicide\b",
    r"\bself[\s-]harm\b",
    r"\bno\s+one\s+cares\b",
    r"\bnobody\s+loves\b",
    r"\bi\s+hate\s+(my\s+life|myself)\b",
    r"\bkuch\s+nahi\s+rehna\b",          # Hindi distress
    r"\bjeena\s+nahi\b",
    r"\bmarna\s+chahta\b",
]

_HARMFUL_PATTERNS = [
    r"\b(porn|sex(ual)?|naked|nude)\b",
    r"\b(gun|weapon|bomb|explosive|kill\s+someone)\b",
    r"\b(drug|cocaine|heroin|weed|ganja)\b",
]

_DISTRESS_RE = re.compile("|".join(_DISTRESS_PATTERNS), re.IGNORECASE)
_HARMFUL_RE = re.compile("|".join(_HARMFUL_PATTERNS), re.IGNORECASE)

_DISTRESS_RESPONSE = (
    "Ek second ruko. Tumse baat karni hai. "
    "Agar tumhare mann mein koi bura khayal aa raha hai, to kisi bade ko batao — "
    "apni mummy, papa, ya kisi trusted adult ko. "
    "iCall helpline: 9152987821 (free, Hindi/English). "
    "Tum akele nahi ho. 💙"
)

_BLOCK_RESPONSE = (
    "Yeh topic Parth ke bahar hai! "
    "Chalte hain apni padhai par — koi sawaal hai Maths, Science, ya kisi aur subject ka?"
)


class ModerationOpsModule(Module):
    name = "moderation.ops"
    handles = ["interaction.requested"]

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        # Determine whether we are checking input (pre) or output (post)
        checking_output = bool(ctx.response_text)

        text = ctx.response_text if checking_output else ctx.message

        if not checking_output:
            # ── Input check ─────────────────────────────────────────────────
            if _DISTRESS_RE.search(text):
                log.warning(
                    "distress_detected",
                    learner_id=ctx.learner_id,
                    request_id=ctx.request_id,
                )
                await self._flag(ctx, "distress_detected")
                return ModuleResult(
                    veto=True,
                    veto_response=_DISTRESS_RESPONSE,
                    data={"distress_detected": True},
                )

            if _HARMFUL_RE.search(text):
                log.warning(
                    "input_blocked",
                    learner_id=ctx.learner_id,
                    request_id=ctx.request_id,
                )
                await self._flag(ctx, "input_blocked")
                return ModuleResult(
                    veto=True,
                    veto_response=_BLOCK_RESPONSE,
                    data={"distress_detected": False},
                )

            return ModuleResult(data={"moderation_ok": True, "distress_detected": False})

        else:
            # ── Output check ─────────────────────────────────────────────────
            if _HARMFUL_RE.search(text):
                log.error(
                    "output_flagged",
                    learner_id=ctx.learner_id,
                    request_id=ctx.request_id,
                )
                await self._flag(ctx, "output_flagged")
                return ModuleResult(
                    veto=True,
                    veto_response=_BLOCK_RESPONSE,
                    data={},
                )

            return ModuleResult(data={"output_moderation_ok": True})

    async def _flag(self, ctx: KernelContext, event_type: str):
        if ctx.db:
            try:
                from foundation.outbox import publish
                await publish(
                    ctx.db, f"moderation.{event_type}",
                    {"learner_id": ctx.learner_id, "request_id": ctx.request_id},
                    aggregate="learner", aggregate_id=ctx.learner_id,
                )
            except Exception as e:
                log.warning("moderation_flag_publish_failed", event_type=event_type, error=str(e))

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass  # moderation.ops holds no PII
