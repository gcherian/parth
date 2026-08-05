import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from modules.teacher.routes import _staleness_note  # noqa: E402


class TeacherPortraitStalenessTests(unittest.TestCase):
    def test_recent_observation_gets_no_note(self):
        submitted = datetime.now(timezone.utc) - timedelta(days=5)
        self.assertEqual(_staleness_note(submitted), "")

    def test_missing_timestamp_gets_no_note(self):
        self.assertEqual(_staleness_note(None), "")

    def test_moderately_old_observation_gets_a_soft_weeks_note(self):
        submitted = datetime.now(timezone.utc) - timedelta(days=45)
        note = _staleness_note(submitted)
        self.assertIn("weeks ago", note)
        self.assertNotIn("outdated", note)

    def test_very_old_observation_gets_an_explicit_outdated_warning(self):
        submitted = datetime.now(timezone.utc) - timedelta(days=240)
        note = _staleness_note(submitted)
        self.assertIn("months ago", note)
        self.assertIn("outdated", note)


if __name__ == "__main__":
    unittest.main()
