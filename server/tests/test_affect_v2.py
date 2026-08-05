import sys
import unittest
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.learner_state.affect_v2 import absorb_turn  # noqa: E402


class FakeAffectConn:
    """Stands in for the one row this module reads/writes — no real DB."""

    def __init__(self):
        self.row = None

    async def fetchrow(self, _query, _learner_id):
        return self.row

    async def execute(self, _query, _learner_id, valence, intensity, history, gear_shift):
        self.row = {"valence": valence, "intensity": intensity, "affect_history": history,
                    "affect_gear_shift": gear_shift}


class AffectV2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_state_carries_across_turns_instead_of_being_overwritten(self):
        conn = FakeAffectConn()

        first = await absorb_turn(conn, "learner-1", "this is so hard, I give up")
        second = await absorb_turn(conn, "learner-1", "this is so hard, I give up")

        # A repeated frustrated turn should push valence further negative when
        # the previous state is carried forward — the exact fix over the old
        # "last_emotion = new_label" overwrite this replaces.
        self.assertLess(second["valence"], first["valence"])

    async def test_persists_a_row_for_a_new_learner_with_no_prior_state(self):
        conn = FakeAffectConn()
        self.assertIsNone(conn.row)

        result = await absorb_turn(conn, "learner-new", "what if we tried a different way")

        self.assertIsNotNone(conn.row)
        self.assertEqual(conn.row["valence"], result["valence"])
        self.assertIn("gear_shift", result)

    async def test_gear_shift_fires_on_a_sustained_frustration_ramp(self):
        conn = FakeAffectConn()
        result = {}
        for _ in range(3):
            result = await absorb_turn(conn, "learner-2", "too hard, i cant do this, ugh")

        self.assertEqual(result["gear_shift"], "frustration_ramp -> simplify_or_hint_now")


if __name__ == "__main__":
    unittest.main()
