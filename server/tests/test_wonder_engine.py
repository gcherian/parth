"""
Tests for wonder.engine (modules/wonder_engine/). Pure-function tests
only — bridges.py's selection logic runs entirely against the in-memory
puzzle library (puzzle_engine/loader.py), no DB needed. Same convention
as test_meaning_graph.py / test_mag_memory.py's pure-function tests.
"""
import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.wonder_engine import bridges  # noqa: E402
from modules.puzzle_engine.cold_start import bridge_for  # noqa: E402
from modules.puzzle_engine.loader import SPHERES  # noqa: E402


class HomeSphereTests(unittest.TestCase):
    def test_science_maps_to_physics(self):
        self.assertEqual(bridges.home_sphere("Science"), "physics")

    def test_maths_maps_to_mathematics(self):
        self.assertEqual(bridges.home_sphere("Maths"), "mathematics")
        self.assertEqual(bridges.home_sphere("Math"), "mathematics")

    def test_unknown_subject_falls_back_to_default(self):
        self.assertEqual(bridges.home_sphere("General"), "philosophy_logic")

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(bridges.home_sphere("  SCIENCE  "), "physics")


class LevelForGradeTests(unittest.TestCase):
    def test_young_grade_is_beginner(self):
        self.assertEqual(bridges.level_for_grade(4), "beginner")
        self.assertEqual(bridges.level_for_grade(6), "beginner")

    def test_middle_grade_is_intermediate(self):
        self.assertEqual(bridges.level_for_grade(7), "intermediate")
        self.assertEqual(bridges.level_for_grade(10), "intermediate")

    def test_senior_grade_is_advanced(self):
        self.assertEqual(bridges.level_for_grade(11), "advanced")
        self.assertEqual(bridges.level_for_grade(12), "advanced")


class BridgeForTests(unittest.TestCase):
    def test_every_sphere_has_a_bridge_target(self):
        for sphere in SPHERES:
            target = bridge_for(sphere)
            self.assertIn(target, SPHERES, f"{sphere} -> {target} is not a real sphere")

    def test_bridge_is_a_different_sphere_than_the_input(self):
        # A "cross-domain" bridge that maps a sphere to itself defeats the point.
        for sphere in SPHERES:
            self.assertNotEqual(bridge_for(sphere), sphere)


class SelectBridgePuzzleTests(unittest.TestCase):
    def test_returns_a_puzzle_for_a_common_subject(self):
        puzzle = bridges.select_bridge_puzzle("Science", grade=8, exclude_ids=set())
        self.assertIsNotNone(puzzle)
        self.assertIn("hook", puzzle)
        self.assertIn("discover", puzzle)

    def test_excluded_ids_are_never_returned(self):
        first = bridges.select_bridge_puzzle("Science", grade=8, exclude_ids=set())
        self.assertIsNotNone(first)
        second = bridges.select_bridge_puzzle("Science", grade=8, exclude_ids={first["id"]})
        self.assertIsNotNone(second)
        self.assertNotEqual(first["id"], second["id"])

    def test_bridged_sphere_differs_from_subjects_home_sphere(self):
        puzzle = bridges.select_bridge_puzzle("Science", grade=8, exclude_ids=set())
        self.assertNotEqual(puzzle["sphere"], bridges.home_sphere("Science"))

    def test_falls_back_when_all_puzzles_at_exact_level_are_excluded(self):
        home = bridges.home_sphere("Science")
        target_sphere = bridge_for(home)
        from modules.puzzle_engine import loader
        exact_level = bridges.level_for_grade(8)
        all_at_level = {p["id"] for p in loader.for_sphere_level(target_sphere, exact_level)}
        puzzle = bridges.select_bridge_puzzle("Science", grade=8, exclude_ids=all_at_level)
        self.assertIsNotNone(puzzle)
        self.assertNotIn(puzzle["id"], all_at_level)


class FormatTests(unittest.TestCase):
    def test_wonder_offer_includes_hook_and_never_states_the_answer_as_a_directive(self):
        puzzle = {"hook": "Can gravity bend light?", "discover": "Light follows curved spacetime."}
        text = bridges.format_wonder_offer(puzzle)
        self.assertIn(puzzle["hook"], text)
        self.assertIn("don't just state it", text.lower().replace("don’t", "don't"))

    def test_wonder_offer_explicitly_says_never_force_it(self):
        puzzle = {"hook": "h", "discover": "d"}
        text = bridges.format_wonder_offer(puzzle)
        self.assertIn("never force it", text)

    def test_belief_exploration_includes_the_hint_and_avoids_leading_with_correction(self):
        text = bridges.format_belief_exploration("heavier things fall faster")
        self.assertIn("heavier things fall faster", text)
        self.assertIn("Before correcting", text)


if __name__ == "__main__":
    unittest.main()
