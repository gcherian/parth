"""
attention.federated — Population-level learning priors.

Maintains aggregate concept difficulty and effective analogy mappings across
all learners without exposing individual data. Currently stores local aggregates
only; cross-deployment gradient sharing is a future Sprint 5 feature.
"""
import json
from pathlib import Path

from config import Config
from kernel.context import Event, KernelContext, ModuleResult
from kernel.module import Module
from foundation.observability import get_logger
from foundation.outbox import subscribe

log = get_logger("attention.federated")

_PRIORS_FILE = Config.DATA_DIR / "federated_priors.json"


def _load_priors() -> dict:
    if _PRIORS_FILE.exists():
        try:
            return json.loads(_PRIORS_FILE.read_text())
        except Exception:
            pass
    return {"concept_difficulty": {}, "analogy_effectiveness": {}}


def _save_priors(priors: dict):
    _PRIORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PRIORS_FILE.write_text(json.dumps(priors, indent=2))


class AttentionFederatedModule(Module):
    name = "attention.federated"
    handles = []  # does not participate in the critical path

    def __init__(self):
        self._priors = _load_priors()
        subscribe("learner.state_updated", self._on_state_updated)

    async def handle(self, event: Event, ctx: KernelContext) -> ModuleResult:
        return ModuleResult(data={})

    def get_prior_difficulty(self, concept_id: str) -> float:
        """Returns population-average difficulty (0=easy, 1=hard). Default 0.5."""
        return self._priors["concept_difficulty"].get(concept_id, 0.5)

    def get_prior_analogy_effectiveness(self, domain: str) -> float:
        """Returns population-average analogy effectiveness score 1-10. Default 5.0."""
        return self._priors["analogy_effectiveness"].get(domain, 5.0)

    async def _on_state_updated(self, event_type: str, payload: dict):
        """Update population priors from anonymised learner signals."""
        concept_id = payload.get("concept_id")
        p_mastery  = payload.get("p_mastery")
        domain     = payload.get("analogy_domain")
        engagement = payload.get("engagement")

        if concept_id and p_mastery is not None:
            # Aggregate difficulty = 1 - mastery, EMA with alpha=0.05
            old = self._priors["concept_difficulty"].get(concept_id, 0.5)
            self._priors["concept_difficulty"][concept_id] = round(
                0.95 * old + 0.05 * (1.0 - p_mastery), 3
            )

        if domain and engagement is not None:
            old = self._priors["analogy_effectiveness"].get(domain, 5.0)
            self._priors["analogy_effectiveness"][domain] = round(
                0.95 * old + 0.05 * engagement, 2
            )

        _save_priors(self._priors)

    async def on_erase(self, learner_id: str, ctx: KernelContext):
        pass  # only aggregate data, no per-learner rows
