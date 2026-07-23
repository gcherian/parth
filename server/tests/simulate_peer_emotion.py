"""
Simulate simulated students interacting with EACH OTHER (peer-to-peer), not
with the tutor, to explore how the continuous emotion engine's trust-weighted
contagion behaves. See modules/learner_state/EMOTION_MODEL_V2_DESIGN.md.

This is intentionally offline: no server, DB, or LLM call required. Each
persona's existing scripted `messages` (tests/personas.py) are treated as
things said aloud to a peer rather than to the tutor — the point is to
exercise the emotion engine's dynamics (self-appraisal + trust-scaled
contagion + the D'Mello-weighted transition graph), not to generate new
dialogue content.

Usage:
    cd server
    python tests/simulate_peer_emotion.py                       # default pair, trust=0.7
    python tests/simulate_peer_emotion.py meera_s7 vikram_s10 --trust 0.2
    python tests/simulate_peer_emotion.py meera_s7 vikram_s10 --sweep
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.personas import get_persona
from modules.learner_state.emotion_engine import StudentEmotionEngine


def run_pair(id_a: str, id_b: str, trust: float, seed: int = 7, verbose: bool = True):
    a = get_persona(id_a)
    b = get_persona(id_b)
    if not a or not b:
        raise SystemExit(f"unknown persona id(s): {id_a}, {id_b}")

    eng_a = StudentEmotionEngine(student_id=a["id"], seed=seed)
    eng_b = StudentEmotionEngine(student_id=b["id"], seed=seed + 1)

    if verbose:
        print(f"\n{'=' * 78}")
        print(f"  {a['avatar']} {a['name']}  <->  {b['avatar']} {b['name']}   (trust={trust:.2f})")
        print(f"{'=' * 78}")
        print(f"{'turn':<5}{'speaker':<10}{'line':<48}{'v':>6}{'i':>6}  gear shift")

    n_turns = min(len(a["messages"]), len(b["messages"]))
    for t in range(n_turns):
        # Each speaks their own scripted line (self-appraisal); the listener
        # gets a trust-scaled contagion pull toward the speaker's new state.
        for speaker_id, speaker_eng, other_eng, line in (
            (a["id"], eng_a, eng_b, a["messages"][t]),
            (b["id"], eng_b, eng_a, b["messages"][t]),
        ):
            speaker_eng.absorb_text(line)
            other_eng.absorb_contagion(speaker_eng.state, trust)

            if verbose:
                preview = (line[:45] + "...") if len(line) > 48 else line
                gs = speaker_eng.gear_shift()
                print(f"{t:<5}{speaker_id.split('_')[0]:<10}{preview:<48}"
                      f"{speaker_eng.state.valence:>6.2f}{speaker_eng.state.intensity:>6.2f}  {gs}")

    if verbose:
        print()
        print(f"  final: {a['name']} = {eng_a.label} (v={eng_a.state.valence:.2f}, i={eng_a.state.intensity:.2f})"
              f"   |   {b['name']} = {eng_b.label} (v={eng_b.state.valence:.2f}, i={eng_b.state.intensity:.2f})")
        gap = abs(eng_a.state.valence - eng_b.state.valence)
        print(f"  final valence gap: {gap:.2f}  (lower = more convergence)")

    return eng_a, eng_b


def convergence_sweep(id_a: str, id_b: str, n_seeds: int = 25) -> None:
    """Reports final valence gap for the given persona pair across trust
    levels. NOTE: persona scripts are scripted monologues toward a tutor, not
    turn-aligned dialogue with each other — their emotional arcs run on their
    own independent schedules, so contagion at a mismatched moment can push
    two people apart as easily as together. This is real, not noise: it means
    the persona pair is a qualitative flavor demo, not proof of the contagion
    mechanism. See controlled_convergence_check() for the isolated version of
    that claim."""
    print(f"\nConvergence vs. trust for {id_a} <-> {id_b}  (mean final valence gap over {n_seeds} seeds):")
    print(f"{'trust':>7}  {'mean gap':>10}")
    for trust in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        gaps = []
        for seed in range(n_seeds):
            eng_a, eng_b = run_pair(id_a, id_b, trust, seed=seed, verbose=False)
            gaps.append(abs(eng_a.state.valence - eng_b.state.valence))
        print(f"{trust:>7.1f}  {sum(gaps) / len(gaps):>10.3f}")


def controlled_convergence_check(n_seeds: int = 30, n_turns: int = 6) -> None:
    """Confound-free version of the Hatfield contagion prediction: one
    synthetic student repeatedly says something frustrated, the other
    repeatedly says something neutral, turn-aligned by construction (unlike
    the persona pair). This isolates the contagion mechanism itself from
    persona-script phase mismatches and should show final valence gap
    shrinking monotonically as trust rises."""
    print(f"\nControlled contagion check (mean final valence gap over {n_seeds} seeds):")
    print(f"{'trust':>7}  {'mean gap':>10}")
    for trust in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        gaps = []
        for seed in range(n_seeds):
            eng_a = StudentEmotionEngine(student_id="frustrated_synthetic", seed=seed)
            eng_b = StudentEmotionEngine(student_id="neutral_synthetic", seed=seed + 1000)
            for _ in range(n_turns):
                eng_a.absorb_text("I give up, this is too hard, I can't do it")
                eng_b.absorb_text("okay, let's keep going with the next part")
                eng_b.absorb_contagion(eng_a.state, trust)
                eng_a.absorb_contagion(eng_b.state, trust)
            gaps.append(abs(eng_a.state.valence - eng_b.state.valence))
        print(f"{trust:>7.1f}  {sum(gaps) / len(gaps):>10.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("id_a", nargs="?", default="meera_s7")
    parser.add_argument("id_b", nargs="?", default="vikram_s10")
    parser.add_argument("--trust", type=float, default=0.7, help="0 = strangers, 1 = close friends")
    parser.add_argument("--sweep", action="store_true", help="also print convergence vs. trust (persona pair, qualitative)")
    parser.add_argument("--controlled", action="store_true", help="run the confound-free synthetic contagion check")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    run_pair(args.id_a, args.id_b, args.trust, seed=args.seed)
    if args.sweep:
        convergence_sweep(args.id_a, args.id_b)
    if args.controlled:
        controlled_convergence_check()


if __name__ == "__main__":
    main()
