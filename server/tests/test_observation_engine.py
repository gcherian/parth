import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.observation_engine.service import (  # noqa: E402
    _build_prompt,
    _concept_hint,
    _extract_json,
    _register_hint,
    _tone_note,
    Probe,
    ObservationResult,
)


class ObservationEngineTests(unittest.TestCase):
    def test_register_hint_flags_exam_prep_at_grade_11_plus(self):
        self.assertIn("IIT/NEET", _register_hint(11))
        self.assertIn("IIT/NEET", _register_hint(12))
        self.assertNotIn("IIT/NEET", _register_hint(9))
        self.assertNotIn("IIT/NEET", _register_hint(6))

    def test_tone_note_drops_exclamation_register_for_teens(self):
        self.assertNotIn("encouraging", _tone_note(12))
        self.assertIn("no baby talk", _tone_note(11))
        self.assertIn("warm", _tone_note(6))

    def test_concept_hint_empty_when_no_candidates(self):
        self.assertEqual(_concept_hint([]), "")

    def test_concept_hint_lists_ids_when_candidates_present(self):
        hint = _concept_hint([{"id": "ratios", "label": "Ratios and Proportions"}])
        self.assertIn("ratios", hint)
        self.assertIn("Ratios and Proportions", hint)

    def test_build_prompt_includes_the_observation_verbatim(self):
        prompt = _build_prompt("A dog chased a cat.", 12, [])
        self.assertIn("A dog chased a cat.", prompt)
        self.assertIn("grade level: 12", prompt)

    def test_build_prompt_truncates_very_long_observations(self):
        prompt = _build_prompt("x" * 5000, 6, [])
        # 1000-char cap on the observation itself, not on the whole prompt.
        self.assertLess(prompt.count("x"), 1500)

    def test_extract_json_handles_surrounding_prose(self):
        raw = 'Sure, here you go:\n{"probes": [], "opening_message": "hi"}\nHope that helps!'
        data = _extract_json(raw)
        self.assertEqual(data["opening_message"], "hi")

    def test_extract_json_raises_on_no_json_present(self):
        with self.assertRaises(ValueError):
            _extract_json("no json here at all")

    def test_extract_json_raises_on_truncated_json(self):
        # The exact failure mode hit against the live Ollama backend during
        # manual testing before temperature/num_ctx were tuned — a response
        # cut off mid-object. Locking in that this fails loudly (triggering
        # generate_cross_domain_probes' retry-once path) rather than
        # silently returning partial data.
        with self.assertRaises(Exception):
            _extract_json('{"probes": [{"domain": "Biology", "opening_question": "why')


class ProbeDataclassTests(unittest.TestCase):
    def test_probe_defaults_concept_ids_to_empty_list_not_shared_mutable(self):
        a = Probe(domain="physics", opening_question="q1", why_this_angle="w1")
        b = Probe(domain="chemistry", opening_question="q2", why_this_angle="w2")
        a.concept_ids.append("only_a")
        self.assertEqual(b.concept_ids, [])

    def test_observation_result_holds_probes_and_opening_message(self):
        probes = [Probe(domain="biology", opening_question="q", why_this_angle="w")]
        result = ObservationResult(probes=probes, opening_message="q")
        self.assertEqual(len(result.probes), 1)
        self.assertEqual(result.opening_message, "q")


if __name__ == "__main__":
    unittest.main()
