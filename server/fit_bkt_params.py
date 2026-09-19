"""
fit_bkt_params.py — fit the pooled global BKT parameters against
learner_state.kt_events and write them to learner_state.bkt_params.

Methodology
-----------
Grid search (not EM) over (p_init, p_transit, p_slip, p_guess), maximizing
total log-likelihood of the observed sequence of correct/incorrect BKT
observations. Grid search was chosen over EM for this codebase deliberately:
it's ~40 lines of pure Python with no new dependency (no numpy/scipy in
requirements.txt), it's trivially correct to read and audit, and at Parth's
current data volume (low hundreds of events) the extra precision EM buys
over a reasonably fine grid isn't worth the added machinery. Revisit if/when
kt_events grows into the thousands and grid search starts being the
bottleneck.

"Observation" here means exactly what knowledge.py's record_demonstration /
record_misconception treat as a BKT observation: a concept gets an
observation in a turn iff it's the turn's flagged misconception concept
(incorrect) or the turn had no misconception at all (correct). A concept
that merely co-occurred in a turn where a *different* concept had the
misconception gets no observation that turn (record_exposure only) — see
knowledge.py's module docstring and docs/model_of_the_child_2026_09_18.md
§3.4 ("same-turn credit gaps"). This must match eval_knowledge_model.py's
replay exactly, or the two tools would be scoring/fitting against different
definitions of "what happened."

Usage
-----
    cd server && source venv/bin/activate
    python fit_bkt_params.py                  # fit + write the '_global_' row
    python fit_bkt_params.py --dry-run         # fit and print only, no write

Re-run this after kt_events has grown meaningfully (a few hundred more
events) to refit — knowledge.get_params() always reads whatever is
currently in the table, so a refit takes effect on the next request with no
code change.
"""
from __future__ import annotations

import argparse
import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from foundation.db import get_pool, close_pool
from modules.learner_state.bkt import BKTParams, LITERATURE_DEFAULTS, initial, update, predict_correct

console = Console()


@dataclass
class Observation:
    prior_index: int  # 0-based position of this observation in its (learner, concept) sequence
    correct: bool


async def fetch_observation_sequences(pool) -> list[list[bool]]:
    """One list[bool] per (learner_id, concept_id) — True/False in
    chronological order — using the same turn-reconstruction and
    same-turn-credit-gap exclusion rule as eval_knowledge_model.py."""
    rows = await pool.fetch(
        """
        SELECT learner_id, concept_id, correct, created_at
        FROM learner_state.kt_events
        ORDER BY learner_id, created_at
        """
    )
    by_learner: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_learner[r["learner_id"]][r["created_at"]].append(r)

    sequences: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for learner_id, by_ts in by_learner.items():
        for ts in sorted(by_ts.keys()):
            turn = by_ts[ts]
            misconception_concepts = {r["concept_id"] for r in turn if not r["correct"]}
            has_misconception = bool(misconception_concepts)
            for row in turn:
                cid = row["concept_id"]
                if has_misconception and cid not in misconception_concepts:
                    continue  # same-turn credit gap — no observation for this concept
                sequences[(learner_id, cid)].append(bool(row["correct"]))

    return list(sequences.values())


def log_likelihood(sequences: list[list[bool]], params: BKTParams) -> float:
    total = 0.0
    eps = 1e-9
    for seq in sequences:
        prior = initial(params)
        for correct in seq:
            p_correct = predict_correct(prior, params)
            p_correct = min(max(p_correct, eps), 1 - eps)
            total += math.log(p_correct) if correct else math.log(1 - p_correct)
            prior = update(prior, correct, params)
    return total


# Regularization strength for the MAP objective below. Plain MLE on ~150
# observations chases a degenerate corner of parameter space (p_init -> 1,
# p_transit/p_guess -> 0 — "assume every child already knows everything and
# never learns or guesses") because that short a sequence carries almost no
# learning-curve signal; empirically confirmed here by grid_search() hitting
# the edge of an already-wide grid on the first fit against real pilot data.
# A quadratic penalty toward LITERATURE_DEFAULTS turns this into a MAP
# estimate instead of raw MLE — standard practice for small-sample parameter
# fitting. Its influence shrinks automatically as data grows, since the
# log-likelihood term's magnitude scales with n while this penalty's does
# not; no manual re-tuning needed as kt_events accumulates.
REG_LAMBDA = 15.0


def objective(sequences: list[list[bool]], params: BKTParams) -> float:
    penalty = REG_LAMBDA * sum(
        (getattr(params, name) - getattr(LITERATURE_DEFAULTS, name)) ** 2
        for name in ("p_init", "p_transit", "p_slip", "p_guess")
    )
    return log_likelihood(sequences, params) - penalty


# A coarse-but-sensible grid, shared by grid_search() and main()'s edge-hit
# check below. p_slip/p_guess are kept below 0.5 by construction — above
# that the parameter is doing the opposite of what its name says and the
# model becomes unidentifiable.
PARAM_GRIDS = {
    "p_init":    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    "p_transit": [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4],
    "p_slip":    [0.02, 0.05, 0.1, 0.15, 0.2, 0.3],
    "p_guess":   [0.02, 0.05, 0.1, 0.2, 0.3, 0.4],
}


def grid_search(sequences: list[list[bool]]) -> tuple[BKTParams, float]:
    """Selects by the regularized objective (MAP), but returns the actual
    (unpenalized) log-likelihood of the winner for honest reporting."""
    best_params = None
    best_obj = float("-inf")
    for p_init in PARAM_GRIDS["p_init"]:
        for p_transit in PARAM_GRIDS["p_transit"]:
            for p_slip in PARAM_GRIDS["p_slip"]:
                for p_guess in PARAM_GRIDS["p_guess"]:
                    params = BKTParams(p_init, p_transit, p_slip, p_guess)
                    obj = objective(sequences, params)
                    if obj > best_obj:
                        best_obj = obj
                        best_params = params
    return best_params, log_likelihood(sequences, best_params)


async def main(dry_run: bool):
    pool = await get_pool()
    try:
        sequences = await fetch_observation_sequences(pool)
        n_events = sum(len(s) for s in sequences)
        if n_events < 20:
            console.print(
                f"[red]Only {n_events} fittable observations across "
                f"{len(sequences)} (learner, concept) sequences — too few to "
                "fit reliably. Run more sessions first, or lower this "
                "script's own floor if you really want a fit anyway.[/red]"
            )
            return

        console.print(
            f"Fitting on [bold]{n_events}[/bold] observations across "
            f"[bold]{len(sequences)}[/bold] (learner, concept) sequences…\n"
        )
        best_params, best_ll = grid_search(sequences)

        table = Table(title="Fitted global BKT parameters")
        table.add_column("Parameter")
        table.add_column("Value", justify="right")
        table.add_column("")
        edge_hits = []
        for name in ("p_init", "p_transit", "p_slip", "p_guess"):
            value = getattr(best_params, name)
            grid = PARAM_GRIDS[name]
            at_edge = value == grid[0] or value == grid[-1]
            if at_edge:
                edge_hits.append(name)
            table.add_row(name, f"{value:.2f}", "⚠ grid edge" if at_edge else "")
        console.print(table)
        console.print(f"Log-likelihood: {best_ll:.2f}  (n={n_events})\n")
        if edge_hits:
            console.print(
                f"[yellow]{', '.join(edge_hits)} landed on the edge of this script's "
                f"search grid — the true optimum may lie outside it. With this little "
                f"data (n={n_events}) that's plausible on its own merits (short "
                f"sequences don't carry much of a learning-curve signal), but widen "
                f"the PARAM_GRIDS in the code above and refit once kt_events has "
                f"grown before trusting these numbers at face value.[/yellow]\n"
            )

        if dry_run:
            console.print("[dim]--dry-run set — not writing to the database.[/dim]")
            return

        await pool.execute(
            """
            INSERT INTO learner_state.bkt_params
                (concept_id, p_init, p_transit, p_slip, p_guess, n_fit, log_likelihood, fitted_at)
            VALUES ('_global_', $1, $2, $3, $4, $5, $6, now())
            ON CONFLICT (concept_id) DO UPDATE SET
                p_init=$1, p_transit=$2, p_slip=$3, p_guess=$4,
                n_fit=$5, log_likelihood=$6, fitted_at=now()
            """,
            best_params.p_init, best_params.p_transit,
            best_params.p_slip, best_params.p_guess,
            n_events, best_ll,
        )
        console.print("[green]Wrote '_global_' row to learner_state.bkt_params.[/green]")
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Fit and print, but don't write to the DB.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
