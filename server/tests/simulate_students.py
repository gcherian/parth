"""
Simulate 15 students interacting with Parth.

Usage:
    cd /Volumes/Seagate/Parth/server
    python tests/simulate_students.py                  # run all 15
    python tests/simulate_students.py arjun_s8         # run one
    python tests/simulate_students.py --report         # print DB state for all learners

After running, check what Parth learned:
    python tests/simulate_students.py --report
"""
import asyncio
import json
import sys
import time
from datetime import datetime

import httpx

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.personas import PERSONAS, get_persona

BASE_URL = "http://localhost:8000"


async def chat(client: httpx.AsyncClient, persona: dict, message: str, history: list) -> dict:
    r = await client.post(
        f"{BASE_URL}/chat",
        json={
            "message": message,
            "history": history,
            "subject": persona["subject"],
            "grade": persona["grade"],
            "learner_id": persona["id"],
            "learner_name": persona["name"],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


async def run_persona(persona: dict, verbose: bool = True) -> dict:
    history = []
    results = []

    if verbose:
        print(f"\n{'═'*60}")
        print(f"  {persona['avatar']}  {persona['name']}  (Grade {persona['grade']}, {persona['subject']})")
        print(f"  {persona['desc']}")
        print(f"{'═'*60}")

    async with httpx.AsyncClient() as client:
        for msg in persona["messages"]:
            if verbose:
                print(f"\n  Child: {msg}")

            t0 = time.time()
            try:
                result = await chat(client, persona, msg, history)
                elapsed = time.time() - t0

                response = result["response"]
                model = result["model"]

                if verbose:
                    # Truncate long responses for readability
                    preview = response[:200] + ("…" if len(response) > 200 else "")
                    print(f"  Parth: {preview}")
                    print(f"  [{model} — {elapsed:.1f}s]")

                history.append({"role": "user", "content": msg})
                history.append({"role": "assistant", "content": response})
                results.append({
                    "message": msg,
                    "response": response,
                    "duration_s": round(elapsed, 2),
                    "model": model,
                })

            except Exception as e:
                if verbose:
                    print(f"  ERROR: {e}")
                results.append({"message": msg, "error": str(e)})

    return {"persona": persona["name"], "results": results}


async def run_all(verbose: bool = True) -> list[dict]:
    summaries = []
    for persona in PERSONAS:
        summary = await run_persona(persona, verbose=verbose)
        summaries.append(summary)
    return summaries


async def print_report():
    """Read back from DB what Parth learned about each child."""
    import asyncpg

    conn = await asyncpg.connect("postgresql://parth:parth_dev@localhost:5432/parth")

    print(f"\n{'═'*70}")
    print("  PARTH LEARNED ABOUT EACH CHILD")
    print(f"{'═'*70}")

    for persona in PERSONAS:
        lid = persona["id"]
        profile = await conn.fetchrow(
            "SELECT total_questions, last_emotion, engagement_score, language_ratio "
            "FROM learner_state.profiles WHERE learner_id=$1", lid
        )
        if not profile:
            continue

        psyche = await conn.fetchrow(
            "SELECT conscientiousness, growth_mindset, anxiety, depth_preference, "
            "extroversion, sample_count FROM learner_state.psyche WHERE learner_id=$1", lid
        )

        episodes = await conn.fetch(
            "SELECT episode_type, LEFT(summary,60) FROM learner_state.episodes "
            "WHERE learner_id=$1 ORDER BY created_at DESC LIMIT 3", lid
        )

        open_loops = await conn.fetch(
            "SELECT LEFT(question,70) FROM learner_state.open_loops "
            "WHERE learner_id=$1 AND status='open'", lid
        )

        knowledge = await conn.fetch(
            "SELECT concept_id, p_mastery FROM learner_state.knowledge "
            "WHERE learner_id=$1 ORDER BY p_mastery DESC LIMIT 3", lid
        )

        print(f"\n  {persona['avatar']}  {persona['name']} (Grade {persona['grade']})")
        print(f"     Questions: {profile['total_questions']}  "
              f"Emotion: {profile['last_emotion']}  "
              f"Engagement: {profile['engagement_score']:.1f}/10  "
              f"Language: {'Hindi' if profile['language_ratio']<0.4 else 'Bilingual' if profile['language_ratio']<0.7 else 'English'}")

        if psyche and psyche['sample_count'] > 0:
            print(f"     Psyche: depth={psyche['depth_preference']:.2f}  "
                  f"growth={psyche['growth_mindset']:.2f}  "
                  f"anxiety={psyche['anxiety']:.2f}  "
                  f"samples={psyche['sample_count']}")

        if knowledge:
            print(f"     Knowledge: {', '.join(f'{r[0]}({r[1]:.2f})' for r in knowledge)}")

        if episodes:
            print("     Episodes:")
            for ep in episodes:
                print(f"       [{ep[0]}] {ep[1]}")

        if open_loops:
            print(f"     Open loop: \"{open_loops[0][0]}\"")

    await conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--report" in args:
        asyncio.run(print_report())
    elif args and not args[0].startswith("--"):
        # Run single persona
        persona = get_persona(args[0])
        if not persona:
            ids = [p["id"] for p in PERSONAS]
            print(f"Unknown persona. Choose from: {', '.join(ids)}")
            sys.exit(1)
        asyncio.run(run_persona(persona, verbose=True))
    else:
        print(f"Running {len(PERSONAS)} student simulations against {BASE_URL}...")
        results = asyncio.run(run_all(verbose=True))
        ok = sum(1 for r in results if not any("error" in x for x in r["results"]))
        print(f"\n✓ {ok}/{len(results)} students completed without errors")
        print("\nRun with --report to see what Parth learned.")
