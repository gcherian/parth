import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.meaning_graph.service import (  # noqa: E402
    age_for_grade,
    build_context,
    graph_to_cypher,
    score_candidate,
)


class MeaningGraphTests(unittest.TestCase):
    def test_age_for_grade_stays_in_first_ten_years(self):
        self.assertEqual(age_for_grade(1), 6)
        self.assertEqual(age_for_grade(8), 10)
        self.assertEqual(age_for_grade("bad"), 8)
        self.assertEqual(age_for_grade(-3), 5)

    def test_score_candidate_matches_story_and_moral_terms(self):
        fox = {
            "title": "The Grapes That Changed Taste",
            "story_label": "The Fox and the Grapes",
            "setup": "A fox wants grapes, fails, then changes the story.",
            "moral_tension": "It is painful to want and fail; truthfulness starts by naming that pain.",
            "nature_bridge": "An echo can distort a sound.",
            "concept_ids": ["concept_evidence_vs_appearance"],
            "motif_ids": ["motif_desire", "motif_truth"],
            "story_tags": ["desire", "excuse", "truth"],
        }
        unrelated = {
            "title": "The Missing One",
            "story_label": "The Lost Sheep",
            "moral_tension": "A group can look fine while one member still needs help.",
            "concept_ids": ["concept_fairness"],
            "motif_ids": ["motif_attention"],
            "story_tags": ["care"],
        }

        query = "Tell a bedtime moral story about truth, desire, and evidence."

        self.assertGreater(score_candidate(query, fox), score_candidate(query, unrelated))

    def test_build_context_formats_parent_and_nature_bridge(self):
        context = build_context([
            {
                "title": "The Brave Pause",
                "story_label": "Arjuna at the Crossroads",
                "tradition": "indian_epic",
                "suspense_question": "Can pausing be brave?",
                "parent_hint": "Ask for a child-scale example.",
                "moral_tension": "Courage is careful action while fear is present.",
                "nature_bridge": "A river changes path without stopping.",
                "motif_ids": ["motif_courage", "motif_identity"],
            }
        ])

        self.assertIn("Meaning graph context", context)
        self.assertIn("Arjuna at the Crossroads", context)
        self.assertIn("Bedtime puzzle suggestion", context)
        self.assertIn("river changes path", context)

    def test_graph_to_cypher_escapes_strings_and_relations(self):
        cypher = graph_to_cypher(
            [
                {
                    "id": "story_lear",
                    "label": "Lear's Test",
                    "kind": "story",
                    "tradition": "shakespeare",
                    "summary": "Quiet truth\nloud praise",
                    "age_min": 8,
                    "age_max": 10,
                    "tags": ["truth", "family"],
                }
            ],
            [
                {
                    "source": "story_lear",
                    "target": "motif_truth",
                    "relation": "teaches",
                    "weight": 0.9,
                    "rationale": "Appearance is not evidence.",
                }
            ],
        )

        self.assertIn("Lear\\'s Test", cypher)
        self.assertIn("Quiet truth\\nloud praise", cypher)
        self.assertIn("[r:TEACHES]", cypher)
        self.assertIn("r.weight = 0.9000", cypher)


if __name__ == "__main__":
    unittest.main()
