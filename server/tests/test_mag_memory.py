"""
Tests for mag.memory (modules/mag_memory/).

Pure-function tests (classify_intent, rrf_fuse, score_transition, linearize)
need no DB or Chroma — same convention as test_meaning_graph.py /
test_teacher_portrait_staleness.py. One integration test exercises
ingest_turn's idempotency against the real local Postgres (this repo's
convention in test_curriculum_retrieval.py — test against real local infra
rather than mocking it), and cleans up its own rows afterward.
"""
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.mag_memory.graph import (  # noqa: E402
    classify_intent,
    rrf_fuse,
    score_transition,
    linearize,
    INTENT_CAUSAL,
    INTENT_TEMPORAL,
    INTENT_ENTITY,
    INTENT_GENERAL,
)


class ClassifyIntentTests(unittest.TestCase):
    def test_why_question_is_causal(self):
        self.assertEqual(classify_intent("why did I get that wrong last time?"), INTENT_CAUSAL)

    def test_when_question_is_temporal(self):
        self.assertEqual(classify_intent("when did we talk about fractions?"), INTENT_TEMPORAL)

    def test_recall_question_is_entity(self):
        self.assertEqual(classify_intent("what did I say about photosynthesis?"), INTENT_ENTITY)

    def test_plain_question_is_general(self):
        self.assertEqual(classify_intent("what is 12 times 7?"), INTENT_GENERAL)

    def test_causal_wins_over_temporal_when_both_present(self):
        # Cause is the harder signal to recover once lost — see graph.py's
        # classify_intent docstring / the paper's ablation (removing causal
        # edges was the single biggest score drop).
        self.assertEqual(classify_intent("why was I confused last time?"), INTENT_CAUSAL)


class RrfFuseTests(unittest.TestCase):
    def test_item_ranked_first_everywhere_scores_highest(self):
        rankings = [["a", "b", "c"], ["a", "c", "b"], ["a", "b", "c"]]
        scores = rrf_fuse(rankings)
        self.assertEqual(max(scores, key=scores.get), "a")

    def test_item_missing_from_a_signal_is_not_penalised_to_zero(self):
        rankings = [["a", "b"], [], ["a"]]
        scores = rrf_fuse(rankings)
        self.assertIn("a", scores)
        self.assertGreater(scores["a"], 0)

    def test_agreement_across_signals_beats_a_single_top_rank(self):
        # "b" is #1 in one ranking only; "a" is #1 in the other two.
        rankings = [["b"], ["a"], ["a"]]
        scores = rrf_fuse(rankings)
        self.assertGreater(scores["a"], scores["b"])


class ScoreTransitionTests(unittest.TestCase):
    def test_causal_edge_scores_higher_under_causal_intent_than_temporal(self):
        causal_score = score_transition("causal", 1.0, INTENT_CAUSAL, hop=1)
        temporal_score = score_transition("temporal", 1.0, INTENT_CAUSAL, hop=1)
        self.assertGreater(causal_score, temporal_score)

    def test_score_decays_with_hop_distance(self):
        near = score_transition("semantic", 1.0, INTENT_GENERAL, hop=1)
        far = score_transition("semantic", 1.0, INTENT_GENERAL, hop=3)
        self.assertGreater(near, far)

    def test_stored_edge_weight_scales_the_score(self):
        strong = score_transition("semantic", 0.9, INTENT_GENERAL, hop=1)
        weak = score_transition("semantic", 0.3, INTENT_GENERAL, hop=1)
        self.assertGreater(strong, weak)


class LinearizeTests(unittest.TestCase):
    def test_empty_nodes_returns_empty_string(self):
        self.assertEqual(linearize([], INTENT_GENERAL), "")

    def test_nodes_are_ordered_chronologically_not_by_score(self):
        now = datetime.now(timezone.utc)
        nodes = [
            {"id": "11111111-aaaa", "content": "second thing", "ts": now, "score": 0.9},
            {"id": "22222222-bbbb", "content": "first thing", "ts": now - timedelta(days=1), "score": 0.1},
        ]
        text = linearize(nodes, INTENT_GENERAL)
        self.assertLess(text.index("first thing"), text.index("second thing"))

    def test_includes_a_short_provenance_ref(self):
        now = datetime.now(timezone.utc)
        nodes = [{"id": "abcdef12-3456-7890", "content": "hello", "ts": now, "score": 1.0}]
        text = linearize(nodes, INTENT_GENERAL)
        self.assertIn("ref:abcdef12", text)


class IngestIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    """Exercises ingest_turn against the real local Postgres (per this repo's
    convention — see test_curriculum_retrieval.py). Skips cleanly if Postgres
    isn't reachable rather than failing the whole suite."""

    async def asyncSetUp(self):
        try:
            import foundation.db as db_mod
            # IsolatedAsyncioTestCase gives each test its own event loop, but
            # asyncpg connections are bound to the loop they were opened on.
            # A graceful close_pool() on a pool from a *previous* (now-closed)
            # test loop raises "Event loop is closed" itself, so just drop
            # the reference — the dead connections are simply garbage
            # collected — and let get_pool() build a fresh one on this loop.
            db_mod._pool = None
            await db_mod.apply_schema()
            self.pool = await db_mod.get_pool()
        except Exception as e:
            self.skipTest(f"Postgres not available: {e}")
        self.learner_id = f"test-mag-{uuid.uuid4()}"

    async def asyncTearDown(self):
        if getattr(self, "pool", None):
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM mag_memory.nodes WHERE learner_id = $1", self.learner_id
                )

    async def test_same_request_id_does_not_create_a_second_node(self):
        from modules.mag_memory.ingest import ingest_turn

        request_id = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            first, _ = await ingest_turn(
                conn, self.learner_id, request_id, "why does ice float?", "Because it's less dense.", []
            )
            second, _ = await ingest_turn(
                conn, self.learner_id, request_id, "why does ice float?", "Because it's less dense.", []
            )
            self.assertIsNotNone(first)
            self.assertEqual(first, second)

            count = await conn.fetchval(
                "SELECT count(*) FROM mag_memory.nodes WHERE learner_id = $1", self.learner_id
            )
            self.assertEqual(count, 1)

    async def test_second_turn_gets_a_temporal_edge_from_the_first(self):
        from modules.mag_memory.ingest import ingest_turn

        async with self.pool.acquire() as conn:
            first_id, _ = await ingest_turn(
                conn, self.learner_id, str(uuid.uuid4()), "what is a fraction?", "Part of a whole.", []
            )
            second_id, _ = await ingest_turn(
                conn, self.learner_id, str(uuid.uuid4()), "what is a decimal?", "Another way to write a fraction.", []
            )
            edge = await conn.fetchrow(
                "SELECT 1 FROM mag_memory.edges WHERE src_id = $1::uuid AND dst_id = $2::uuid AND edge_type = 'temporal'",
                first_id, second_id,
            )
            self.assertIsNotNone(edge)


if __name__ == "__main__":
    unittest.main()
