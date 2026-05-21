"""
Knowledge state management — per-concept Bayesian mastery tracking.

p_mastery formula (simplified BKT):
  p = demonstrations / max(1, exposures)  *  (1 - 0.4 * misconceptions / max(1, exposures))
  clamped to [0.05, 0.98]
"""
import json
import logging
from datetime import datetime

from learner.db import get_conn

log = logging.getLogger("parth.knowledge")


def _mastery(rec: dict) -> float:
    exp = max(1, rec["exposures"])
    demo = rec.get("demonstrations", 0)
    misc = rec.get("misconceptions", 0)
    raw = (demo / exp) * (1.0 - 0.4 * misc / exp)
    return round(max(0.05, min(0.98, raw)), 3)


def _load(learner_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT knowledge_state FROM learners WHERE id=?", (learner_id,)
        ).fetchone()
        if row is None:
            return {}
        return json.loads(row["knowledge_state"] or "{}")


def _save(learner_id: str, ks: dict):
    with get_conn() as conn:
        conn.execute(
            "UPDATE learners SET knowledge_state=? WHERE id=?",
            (json.dumps(ks), learner_id),
        )


def record_exposure(learner_id: str, concepts: list[str]):
    """Child asked about these concepts — record exposure, slight uncertainty bump."""
    if not concepts:
        return
    ks = _load(learner_id)
    for cid in concepts:
        rec = ks.get(cid, {"exposures": 0, "demonstrations": 0, "misconceptions": 0})
        rec["exposures"] = rec.get("exposures", 0) + 1
        rec["last_seen"] = datetime.utcnow().date().isoformat()
        rec["p_mastery"] = _mastery(rec)
        ks[cid] = rec
    _save(learner_id, ks)


def record_misconception(learner_id: str, concepts: list[str]):
    """Evaluator found a misconception linked to these concepts."""
    if not concepts:
        return
    ks = _load(learner_id)
    for cid in concepts:
        rec = ks.get(cid, {"exposures": 0, "demonstrations": 0, "misconceptions": 0})
        rec["exposures"] = max(rec.get("exposures", 0), 1)
        rec["misconceptions"] = rec.get("misconceptions", 0) + 1
        rec["last_seen"] = datetime.utcnow().date().isoformat()
        rec["p_mastery"] = _mastery(rec)
        ks[cid] = rec
    _save(learner_id, ks)


def record_demonstration(learner_id: str, concepts: list[str]):
    """Child used a concept correctly — boost mastery."""
    if not concepts:
        return
    ks = _load(learner_id)
    for cid in concepts:
        rec = ks.get(cid, {"exposures": 0, "demonstrations": 0, "misconceptions": 0})
        rec["exposures"] = max(rec.get("exposures", 0), 1)
        rec["demonstrations"] = rec.get("demonstrations", 0) + 1
        rec["last_seen"] = datetime.utcnow().date().isoformat()
        rec["p_mastery"] = _mastery(rec)
        ks[cid] = rec
    _save(learner_id, ks)


def weak_concepts(learner_id: str, threshold: float = 0.5, n: int = 3) -> list[str]:
    """Return concept IDs with p_mastery below threshold, sorted weakest first."""
    ks = _load(learner_id)
    weak = [(cid, rec["p_mastery"]) for cid, rec in ks.items()
            if rec.get("p_mastery", 0) < threshold and rec.get("exposures", 0) >= 2]
    weak.sort(key=lambda x: x[1])
    return [cid for cid, _ in weak[:n]]


def strong_concepts(learner_id: str, threshold: float = 0.75, n: int = 3) -> list[str]:
    """Return concept IDs with p_mastery above threshold."""
    ks = _load(learner_id)
    strong = [(cid, rec["p_mastery"]) for cid, rec in ks.items()
              if rec.get("p_mastery", 0) >= threshold]
    strong.sort(key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in strong[:n]]
