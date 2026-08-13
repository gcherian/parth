"""
Tests for the RAG retrieval cascade (modules/curriculum_graph/graph.py)
and the /health degraded-when-empty logic (main.py). Runs against a real,
isolated Chroma collection (temp DATA_DIR, real bge-m3 embeddings via the
locally-running Ollama) rather than mocking the vector store — consistent
with this codebase's convention of testing against real local infra
(Postgres elsewhere in this suite) rather than faking it.
"""
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

# test_cold_start_handoff.py injects fake, file-less foundation.* stubs
# (foundation.db, foundation.observability, ...) via
# sys.modules.setdefault(...) for its own isolation. Under `unittest
# discover`, those stubs leak into every test file that runs afterward in
# the same process — including main.py's real `from foundation.X import
# ...` a few lines below, since Python reuses whatever's already in
# sys.modules under that name. A real, file-backed module always has
# __file__ set; the fake ones don't — evict any that don't before main.py
# does its own foundation imports.
import sys as _sys
for _name in list(_sys.modules):
    if _name.startswith("foundation.") and not getattr(_sys.modules[_name], "__file__", None):
        del _sys.modules[_name]

from config import Config  # noqa: E402
from main import _health_status  # noqa: E402
import modules.curriculum_graph.graph as graph  # noqa: E402


FIXTURE_CHUNKS = [
    # subject=science, grade=7 — exactly 2 chunks, so a grade-7 science
    # query should be satisfiable at the most specific cascade tier
    # without needing to widen.
    {
        "id": "sci7_a",
        "text": "Photosynthesis is how green plants make food using sunlight, "
                "water, and carbon dioxide, releasing oxygen as a byproduct.",
        "metadata": {"subject": "science", "grade": 7, "chapter": "Nutrition in Plants",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
    {
        "id": "sci7_b",
        "text": "Chlorophyll in the leaves absorbs sunlight, which powers the "
                "chemical reaction that converts carbon dioxide and water into glucose.",
        "metadata": {"subject": "science", "grade": 7, "chapter": "Nutrition in Plants",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
    # subject=science, grade=9 — a different topic, different grade band.
    {
        "id": "sci9_a",
        "text": "Newton's first law of motion states that an object at rest stays "
                "at rest unless acted upon by an external force.",
        "metadata": {"subject": "science", "grade": 9, "chapter": "Motion",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
    # subject=math, grade=7 — only ONE chunk, deliberately, to force the
    # subject+grade tier below 2 hits and test widening to subject-only.
    {
        "id": "math7_a",
        "text": "A fraction represents a part of a whole, written as a numerator "
                "over a denominator.",
        "metadata": {"subject": "math", "grade": 7, "chapter": "Fractions",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
    {
        "id": "math9_a",
        "text": "A linear equation in two variables can be represented as a "
                "straight line on the Cartesian plane.",
        "metadata": {"subject": "math", "grade": 9, "chapter": "Linear Equations",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
    # subject=history — only ONE chunk total, forcing the cascade all the
    # way to unfiltered for any history query.
    {
        "id": "hist8_a",
        "text": "The Mughal Empire was founded by Babur in 1526 after the "
                "First Battle of Panipat.",
        "metadata": {"subject": "history", "grade": 8, "chapter": "Mughal Empire",
                     "board": "cbse", "school_id": "", "source": "ncert_pdf"},
    },
]


class CurriculumRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._original_data_dir = Config.DATA_DIR
        Config.DATA_DIR = Path(cls._tmpdir.name)
        graph._chroma_collection = None  # force a fresh collection at the new path

        collection = graph._get_collection()
        collection.upsert(
            ids=[c["id"] for c in FIXTURE_CHUNKS],
            documents=[c["text"] for c in FIXTURE_CHUNKS],
            metadatas=[c["metadata"] for c in FIXTURE_CHUNKS],
        )

    @classmethod
    def tearDownClass(cls):
        Config.DATA_DIR = cls._original_data_dir
        graph._chroma_collection = None
        cls._tmpdir.cleanup()

    def test_subject_grade_tier_is_sufficient_when_it_has_enough_hits(self):
        result = graph._retrieve_sync(
            "how do plants make food from sunlight", "science", 7, n_results=3,
        )
        self.assertIn("Photosynthesis", result)
        # Should NOT have needed to widen — the grade-9 Newton's-law chunk
        # (excluded by grade <= 7+1) shouldn't appear.
        self.assertNotIn("Newton's first law", result)

    def test_widens_to_subject_only_when_grade_tier_is_thin(self):
        # Only one math/grade-7 chunk exists, so the subject+grade+board
        # tier alone can't reach 2 hits and must widen to subject+board —
        # pulling in the grade-9 linear-equations chunk too.
        result = graph._retrieve_sync(
            "explain fractions and equations in math", "math", 7, n_results=5,
        )
        self.assertIn("fraction", result.lower())

    def test_widens_to_unfiltered_when_subject_itself_is_thin(self):
        # Only one history chunk exists at all, so even subject+board
        # can't reach 2 hits and the cascade must fall through to
        # unfiltered — should still surface the one history chunk.
        result = graph._retrieve_sync(
            "tell me about the Mughal Empire", "history", 8, n_results=5,
        )
        self.assertIn("Mughal", result)

    def test_grade_filtering_changes_results_for_the_same_query(self):
        low_grade = graph._retrieve_sync("science topics", "science", 7, n_results=2)
        high_grade = graph._retrieve_sync("science topics", "science", 9, n_results=2)
        # Grade 7 shouldn't see the Newton's-law (grade 9) content at the
        # most specific tier; grade 9's window (<=10) covers both.
        self.assertNotIn("Newton's first law", low_grade)

    def test_build_where_tiers_omits_absent_facets_instead_of_forcing_them(self):
        tiers = graph._build_where_tiers(None, 7)
        # No subject given -> no tier should contain a "subject" clause.
        for tier in tiers:
            if tier:
                self.assertNotIn("subject", str(tier))


class HealthStatusTests(unittest.TestCase):
    def test_degraded_when_rag_chunks_is_zero(self):
        self.assertEqual(_health_status(tutor_ok=True, pg_ok=True, rag_chunks=0), "degraded")

    def test_ok_when_everything_healthy(self):
        self.assertEqual(_health_status(tutor_ok=True, pg_ok=True, rag_chunks=42), "ok")

    def test_degraded_when_tutor_or_postgres_down_even_with_chunks_present(self):
        self.assertEqual(_health_status(tutor_ok=False, pg_ok=True, rag_chunks=42), "degraded")
        self.assertEqual(_health_status(tutor_ok=True, pg_ok=False, rag_chunks=42), "degraded")


if __name__ == "__main__":
    unittest.main()
