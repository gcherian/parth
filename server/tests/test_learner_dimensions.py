import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

fake_db = types.ModuleType("foundation.db")
fake_db.get_pool = lambda: None
sys.modules.setdefault("foundation.db", fake_db)


class _FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


fake_observability = types.ModuleType("foundation.observability")
fake_observability.get_logger = lambda *_args, **_kwargs: _FakeLogger()
fake_observability.configure_logging = lambda *_args, **_kwargs: None
sys.modules.setdefault("foundation.observability", fake_observability)

from modules.learner_state.agents.learning_velocity import calculate_learning_velocity
from modules.learner_state.agents.motivation_drive import calculate_motivation_drive
from modules.learner_state.agents.social_preference import (
    blend_social_state,
    classify_social_signal,
)
from modules.learner_state.dimensions import build_dimension_payload
from modules.learner_state.value_purpose import (
    extract_value_themes,
    merge_theme_state,
)


class LearnerDimensionSignalTests(unittest.TestCase):
    def test_learning_velocity_uses_zpd_and_not_flat_ratio(self):
        rows = [
            {
                "concept_id": "fractions",
                "exposures": 4,
                "demonstrations": 3,
                "misconceptions": 0,
                "p_mastery": 0.62,
            },
            {
                "concept_id": "decimals",
                "exposures": 3,
                "demonstrations": 1,
                "misconceptions": 1,
                "p_mastery": 0.35,
            },
        ]

        result = calculate_learning_velocity(
            rows,
            [{"correct": True}, {"correct": False}, {"correct": True}],
            weak_threshold=0.5,
            strong_threshold=0.75,
        )

        self.assertIsNotNone(result["score"])
        self.assertGreater(result["confidence"], 0.25)
        self.assertIn("fractions", result["zpd_concepts"])
        self.assertGreaterEqual(result["zpd_distance"], 0.0)
        self.assertIn("recent_correct_rate", result["evidence"])

    def test_motivation_drive_counts_returns_after_difficulty(self):
        now = datetime.now(timezone.utc)
        rows = [
            {
                "created_at": now - timedelta(days=5),
                "engagement": 3.0,
                "emotion": "confused",
                "misconception": "mixed numerator and denominator",
            },
            {
                "created_at": now - timedelta(days=4, hours=18),
                "engagement": 6.5,
                "emotion": "neutral",
                "misconception": "",
            },
            {
                "created_at": now - timedelta(days=1),
                "engagement": 7.0,
                "emotion": "curious",
                "misconception": "",
            },
        ]

        result = calculate_motivation_drive(rows)

        self.assertGreater(result["score"], 0.5)
        self.assertEqual(result["hard_return_count"], 1)
        self.assertEqual(result["return_after_difficulty"], 1.0)

    def test_social_preference_is_direct_message_signal(self):
        signal = classify_social_signal("Can I teach this to my friend after class?")
        state = blend_social_state(None, signal)

        self.assertEqual(signal["marker"], "teach_back")
        self.assertGreater(state["teach_back_preference"], 0.5)
        self.assertEqual(state["sample_count"], 1)

    def test_value_purpose_reflection_extracts_and_merges_themes(self):
        themes = extract_value_themes(
            "I want to build an app to help my family and people in my city."
        )
        state = merge_theme_state(None, themes)

        self.assertIn("building", themes)
        self.assertIn("helping", themes)
        self.assertGreater(state["confidence"], 0.25)
        self.assertIn("building", state["values"])

    def test_dimension_payload_keeps_proxy_and_reflection_statuses_explicit(self):
        payload = build_dimension_payload(
            {
                "puzzle_portrait": {
                    "portrait_json": {
                        "confidence": 0.5,
                        "primary_sphere": "mathematics",
                    }
                },
                "puzzle_stats": {
                    "count": 5,
                    "avg_quality": 2.2,
                    "deeper_rate": 0.4,
                },
                "velocity": {
                    "velocity_score": 0.64,
                    "confidence": 0.5,
                    "zpd_distance": 0.08,
                    "time_to_mastery_turns": 3.5,
                    "sample_size": 10,
                },
                "drive": {
                    "drive_score": 0.7,
                    "confidence": 0.6,
                    "return_after_difficulty": 0.75,
                    "active_days_14": 4,
                    "hard_return_count": 3,
                },
                "social": {
                    "group_preference": 0.7,
                    "solo_preference": 0.45,
                    "teach_back_preference": 0.8,
                    "sample_count": 3,
                    "last_signal": "teach_back",
                },
                "value": {
                    "purpose_themes": {"helping": 0.7},
                    "values_json": ["helping"],
                    "confidence": 0.43,
                    "sample_count": 1,
                },
            },
            "learner-1",
        )

        self.assertEqual(len(payload["dimensions"]), 15)
        by_key = {d["key"]: d for d in payload["dimensions"]}
        self.assertEqual(by_key["cognitive_ability"]["status"], "direct")
        self.assertEqual(by_key["problem_solving_critical_thinking"]["status"], "proxy")
        self.assertEqual(by_key["value_purpose"]["status"], "reflection")
        self.assertEqual(by_key["social_learning_collaboration"]["status"], "direct")
        self.assertGreater(by_key["cognitive_ability"]["confidence"], 0.4)


if __name__ == "__main__":
    unittest.main()
