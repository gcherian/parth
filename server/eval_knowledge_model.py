"""
eval_knowledge_model.py — offline accuracy check for learner_state.knowledge's
mastery model, replayed against learner_state.kt_events.

This is Step 1 of docs/model_of_the_child_2026_09_18.md's roadmap: build the
yardstick *before* changing the mastery formula, so a future change (real BKT,
forgetting, PFA) can be measured against this baseline instead of guessed.

What it does
------------
For each (learner_id, concept_id), replay kt_events in chronological order,
reproducing the exact update rules mastery_tracker.py drives knowledge.py
with — as of docs/model_of_the_child_2026_09_18.md §5 item 2, this is real
per-concept BKT, not the ratio heuristic this script originally scored:

  - every concept mentioned in a turn gets an exposure counter bump, always
    (knowledge.record_exposure) — and, the first time a concept is ever
    mentioned, its p_mastery is seeded at that concept's fitted BKT prior
    (bkt.initial()). Exposure alone is otherwise not a BKT observation and
    does not change p_mastery.
  - if the turn has NO misconception: every concept mentioned gets a BKT
    "correct" observation (knowledge.record_demonstration -> bkt.update()).
  - if the turn HAS a misconception: only the flagged concept gets a BKT
    "incorrect" observation (knowledge.record_misconception -> bkt.update())
    — every OTHER concept mentioned in that same turn gets exposure only, no
    observation, even though its own kt_events row is marked correct=True.
    This is a real quirk in the live system (see
    docs/model_of_the_child_2026_09_18.md §3.3-3.4), not a bug in this
    script — it is reproduced faithfully and reported below as "same-turn
    credit gaps," and fit_bkt_params.py excludes these from what it fits on
    for the same reason.

At each event this script scores the CURRENT (pre-event) p_mastery as a
next-step prediction of that event's correctness — the standard
knowledge-tracing "next interaction" evaluation protocol. The BKT math
(bkt.initial/bkt.update) and the per-concept parameter lookup
(knowledge.get_params) are imported directly from production rather than
reimplemented, so this eval always scores whatever is actually live; it
will not silently drift out of sync with a future edit.

Turns are reconstructed by grouping kt_events on (learner_id, created_at):
the kernel wraps one whole interaction in a single Postgres transaction, and
now() is stable for the lifetime of a transaction, so every kt_events row
written by one turn shares an identical timestamp.

Usage
-----
    cd server && source venv/bin/activate
    python eval_knowledge_model.py
    python eval_knowledge_model.py --min-events 5
    python eval_knowledge_model.py --out data/kt_eval/baseline_2026_09_19.json

Re-run with --out after any change to knowledge.py's formula and diff the
two JSON files' "overall" block to see whether AUC/log-loss actually moved.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from foundation.db import get_pool, close_pool
from modules.learner_state import bkt
from modules.learner_state.knowledge import get_params

console = Console()


# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class Prediction:
    learner_id: str
    concept_id: str
    predicted: float
    actual: float          # 1.0 / 0.0
    prior_exposures: int   # exposures BEFORE this event — the cold-start bucket key
    elapsed_ms: int
    lag_ms: int
    same_turn_credit_gap: bool  # True if this event was marked correct but got no
                                 # BKT observation because another concept in the
                                 # same turn had a misconception


@dataclass
class ConceptState:
    exposures: int = 0
    p_mastery: float | None = None  # None until this concept's first exposure —
                                     # matches production, where the DB row (and
                                     # therefore a real p_mastery) doesn't exist yet


# ── Fetch + turn reconstruction ──────────────────────────────────────────────

async def fetch_rows(pool, min_events: int) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT learner_id, concept_id, correct, elapsed_ms, lag_ms, session_id, created_at
        FROM learner_state.kt_events
        WHERE learner_id IN (
            SELECT learner_id FROM learner_state.kt_events
            GROUP BY learner_id HAVING COUNT(*) >= $1
        )
        ORDER BY learner_id, created_at
        """,
        min_events,
    )
    return [dict(r) for r in rows]


def group_into_turns(rows: list[dict]) -> dict[str, list[list[dict]]]:
    """learner_id -> chronological list of turns; a turn = all kt_events rows
    sharing one (learner_id, created_at) — see module docstring for why that's
    a safe grouping key."""
    by_learner: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_learner[row["learner_id"]][row["created_at"]].append(row)
    turns: dict[str, list[list[dict]]] = {}
    for learner_id, by_ts in by_learner.items():
        ordered_ts = sorted(by_ts.keys())
        turns[learner_id] = [by_ts[ts] for ts in ordered_ts]
    return turns


# ── Replay ────────────────────────────────────────────────────────────────

async def build_params_cache(pool, concept_ids: set[str]) -> dict[str, bkt.BKTParams]:
    return {cid: await get_params(pool, cid) for cid in concept_ids}


def replay_learner(turns: list[list[dict]], params: dict[str, bkt.BKTParams]) -> list[Prediction]:
    state: dict[str, ConceptState] = defaultdict(ConceptState)
    predictions: list[Prediction] = []

    for turn in turns:
        misconception_concepts = {r["concept_id"] for r in turn if not r["correct"]}
        has_misconception = bool(misconception_concepts)

        # 1) score every concept in this turn using its PRE-turn state —
        # bkt.initial() for a concept never seen before, matching what a
        # fresh knowledge.py row would be seeded to.
        for row in turn:
            cid = row["concept_id"]
            s = state[cid]
            predicted = s.p_mastery if s.p_mastery is not None else bkt.initial(params[cid])
            same_turn_gap = (
                row["correct"] and has_misconception and cid not in misconception_concepts
            )
            predictions.append(Prediction(
                learner_id=row["learner_id"],
                concept_id=cid,
                predicted=predicted,
                actual=1.0 if row["correct"] else 0.0,
                prior_exposures=s.exposures,
                elapsed_ms=row["elapsed_ms"] or 0,
                lag_ms=row["lag_ms"] or 0,
                same_turn_credit_gap=same_turn_gap,
            ))

        # 2) record_exposure: bump the counter for every concept, always; seed
        # p_mastery at the BKT prior the first time a concept is ever seen.
        # No further change to p_mastery here — exposure alone isn't a BKT
        # observation.
        for row in turn:
            cid = row["concept_id"]
            s = state[cid]
            if s.p_mastery is None:
                s.p_mastery = bkt.initial(params[cid])
            s.exposures += 1

        if has_misconception:
            for cid in misconception_concepts:
                s = state[cid]
                s.p_mastery = bkt.update(s.p_mastery, False, params[cid])
            # every other concept in the turn keeps the p_mastery seeded (or
            # left untouched) in step 2 — no BKT observation this turn, per
            # knowledge.py's `if not signals.misconception` guard on
            # record_demonstration.
        else:
            for row in turn:
                cid = row["concept_id"]
                s = state[cid]
                s.p_mastery = bkt.update(s.p_mastery, True, params[cid])

    return predictions


# ── Metrics ───────────────────────────────────────────────────────────────

def auc_score(preds: list[float], actuals: list[float]) -> float | None:
    n = len(preds)
    n_pos = sum(1 for a in actuals if a == 1.0)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(n), key=lambda i: preds[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and preds[order[j + 1]] == preds[order[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    sum_ranks_pos = sum(r for r, a in zip(ranks, actuals) if a == 1.0)
    return (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def log_loss(preds: list[float], actuals: list[float], eps: float = 1e-9) -> float:
    total = 0.0
    for p, a in zip(preds, actuals):
        p = min(max(p, eps), 1 - eps)
        total += -(a * math.log(p) + (1 - a) * math.log(1 - p))
    return total / len(preds)


def brier_score(preds: list[float], actuals: list[float]) -> float:
    return sum((p - a) ** 2 for p, a in zip(preds, actuals)) / len(preds)


def summarize(preds: list[Prediction], label_preds: list[float] | None = None) -> dict:
    """label_preds lets a baseline substitute its own prediction column while
    reusing the same `actuals`/bucketing from `preds`."""
    actuals = [p.actual for p in preds]
    values = label_preds if label_preds is not None else [p.predicted for p in preds]
    return {
        "n": len(preds),
        "base_rate": round(sum(actuals) / len(actuals), 4) if actuals else None,
        "auc": (lambda a: round(a, 4) if a is not None else None)(auc_score(values, actuals)),
        "log_loss": round(log_loss(values, actuals), 4),
        "brier": round(brier_score(values, actuals), 4),
    }


def bucket_by_prior_exposure(preds: list[Prediction]) -> dict[str, list[Prediction]]:
    buckets: dict[str, list[Prediction]] = defaultdict(list)
    for p in preds:
        if p.prior_exposures == 0:
            key = "0 (cold start)"
        elif p.prior_exposures <= 2:
            key = "1-2"
        elif p.prior_exposures <= 5:
            key = "3-5"
        else:
            key = "6+"
        buckets[key].append(p)
    return buckets


# ── Baselines ─────────────────────────────────────────────────────────────

def baseline_constant(preds: list[Prediction], value: float) -> list[float]:
    return [value] * len(preds)


def baseline_last_outcome(preds: list[Prediction]) -> list[float]:
    """Predict the previous event's actual outcome for the same (learner,
    concept); 0.5 for a concept's first-ever event."""
    last: dict[tuple[str, str], float] = {}
    out = []
    for p in preds:
        key = (p.learner_id, p.concept_id)
        out.append(last.get(key, 0.5))
        last[key] = p.actual
    return out


# ── Reporting ─────────────────────────────────────────────────────────────

def print_report(preds: list[Prediction]) -> dict:
    overall_actuals = [p.actual for p in preds]
    base_rate = sum(overall_actuals) / len(overall_actuals)

    models = {
        "knowledge.py (BKT, live)": [p.predicted for p in preds],
        "baseline: base rate": baseline_constant(preds, base_rate),
        "baseline: always 0.5": baseline_constant(preds, 0.5),
        "baseline: last outcome": baseline_last_outcome(preds),
    }

    console.print(
        f"\n[bold]{len(preds)}[/bold] events · "
        f"[bold]{len({p.learner_id for p in preds})}[/bold] learners · "
        f"[bold]{len({p.concept_id for p in preds})}[/bold] concepts · "
        f"base rate (overall correct) = [bold]{base_rate:.1%}[/bold]\n"
    )
    if len(preds) < 200:
        console.print(
            "[yellow]Sample size is small — treat every number below as a "
            "first read, not a settled result. Re-run as kt_events grows.[/yellow]\n"
        )

    overall_table = Table(title="Overall — is the live heuristic better than doing nothing?")
    overall_table.add_column("Model")
    overall_table.add_column("n", justify="right")
    overall_table.add_column("AUC", justify="right")
    overall_table.add_column("Log-loss", justify="right")
    overall_table.add_column("Brier", justify="right")
    overall_metrics = {}
    for name, values in models.items():
        m = summarize(preds, values)
        overall_metrics[name] = m
        overall_table.add_row(
            name, str(m["n"]),
            "n/a" if m["auc"] is None else f"{m['auc']:.3f}",
            f"{m['log_loss']:.3f}", f"{m['brier']:.3f}",
        )
    console.print(overall_table)
    console.print(
        "[dim]Lower log-loss/Brier is better. AUC 0.5 = coin flip, 1.0 = perfect "
        "rank-ordering. \"n/a\" means every event in that slice had the same "
        "outcome, so AUC is undefined.[/dim]\n"
    )

    bucket_table = Table(title="By prior exposure count — cold-start behavior")
    bucket_table.add_column("Prior exposures")
    bucket_table.add_column("n", justify="right")
    bucket_table.add_column("Base rate", justify="right")
    bucket_table.add_column("AUC", justify="right")
    bucket_table.add_column("Log-loss", justify="right")
    bucket_metrics = {}
    for key, group in sorted(bucket_by_prior_exposure(preds).items()):
        m = summarize(group)
        bucket_metrics[key] = m
        bucket_table.add_row(
            key, str(m["n"]),
            "n/a" if m["base_rate"] is None else f"{m['base_rate']:.1%}",
            "n/a" if m["auc"] is None else f"{m['auc']:.3f}",
            f"{m['log_loss']:.3f}",
        )
    console.print(bucket_table)

    gaps = [p for p in preds if p.same_turn_credit_gap]
    if gaps:
        console.print(
            f"\n[yellow]{len(gaps)} of {len(preds)} events ({len(gaps)/len(preds):.1%}) "
            "were 'same-turn credit gaps': the concept's own event was correct, but it "
            "got no demonstration credit because a DIFFERENT concept in the same turn "
            "had a misconception. See docs/model_of_the_child_2026_09_18.md §3.4.[/yellow]"
        )

    return {"overall": overall_metrics, "by_prior_exposure": bucket_metrics,
            "same_turn_credit_gaps": len(gaps)}


# ── Entry point ───────────────────────────────────────────────────────────

def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent, text=True,
        ).strip()
    except Exception:
        return None


async def main(min_events: int, out: str | None):
    pool = await get_pool()
    try:
        rows = await fetch_rows(pool, min_events)
        if not rows:
            console.print(
                f"[red]No learners with >= {min_events} kt_events yet. "
                "Lower --min-events or run more simulated/real sessions first.[/red]"
            )
            return
        turns_by_learner = group_into_turns(rows)
        params = await build_params_cache(pool, {r["concept_id"] for r in rows})
        predictions: list[Prediction] = []
        for turns in turns_by_learner.values():
            predictions.extend(replay_learner(turns, params))

        metrics = print_report(predictions)

        if out:
            payload = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "git_commit": _git_commit(),
                "min_events_filter": min_events,
                "n_events": len(predictions),
                "n_learners": len({p.learner_id for p in predictions}),
                "n_concepts": len({p.concept_id for p in predictions}),
                **metrics,
            }
            out_path = Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2))
            console.print(f"\nWrote baseline snapshot to [bold]{out_path}[/bold]")
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--min-events", type=int, default=3,
                         help="Skip learners with fewer than this many total kt_events (default 3).")
    parser.add_argument("--out", type=str, default=None,
                         help="Also write a JSON snapshot to this path, for diffing against a future run.")
    args = parser.parse_args()
    asyncio.run(main(args.min_events, args.out))
