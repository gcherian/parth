import sys
import types
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

fake_db = types.ModuleType("foundation.db")


async def _missing_get_pool():
    raise AssertionError("test must patch identity.get_pool")


fake_db.get_pool = _missing_get_pool
sys.modules.setdefault("foundation.db", fake_db)


class _FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


fake_observability = types.ModuleType("foundation.observability")
fake_observability.get_logger = lambda *_args, **_kwargs: _FakeLogger()
sys.modules.setdefault("foundation.observability", fake_observability)

from foundation import identity
from modules.puzzle_engine.cold_start import get_probe


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self):
        self.identities = {}
        self.guardian_links = {}
        self.profiles = {}

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        if "INSERT INTO foundation.identities" in sql and "'child'" in sql:
            child_id, name, grade, school_id = args
            self.identities[child_id] = {
                "type": "child",
                "name": name,
                "grade": grade,
                "school_id": school_id,
            }
        elif "INSERT INTO foundation.identities" in sql and "'guardian'" in sql:
            guardian_id = args[0]
            self.identities[guardian_id] = {
                "type": "guardian",
                "name": "Pilot Guardian",
            }
        elif "INSERT INTO foundation.guardian_links" in sql:
            guardian_id, child_id, scopes = args
            self.guardian_links[child_id] = {
                "guardian_id": guardian_id,
                "consent_given": True,
                "scope": scopes,
            }
        elif "INSERT INTO learner_state.profiles" in sql:
            learner_id, name, grade = args
            self.profiles[learner_id] = {"name": name, "grade": grade}

    async def fetchrow(self, sql, *args):
        if "SELECT type FROM foundation.identities" in sql:
            row = self.identities.get(args[0])
            return {"type": row["type"]} if row else None
        if "SELECT 1 FROM foundation.identities" in sql:
            row = self.identities.get(args[0])
            return {"?column?": 1} if row and row["type"] == "child" else None
        if "SELECT consent_given, scope" in sql:
            return self.guardian_links.get(args[0])
        return None


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class ColdStartHandoffTests(unittest.TestCase):
    def test_cold_start_serves_five_distinct_probe_steps(self):
        seen_ids = set()
        primary_sphere = None
        modes = []
        probe_numbers = []

        def first(items):
            return items[0]

        with patch("modules.puzzle_engine.cold_start.random.choice", first):
            for total in range(5):
                probe = get_probe(total, seen_ids, primary_sphere, grade=6)
                modes.append(probe["mode"])
                probe_numbers.append(probe["probe"])

                if probe["mode"] == "choice":
                    selected = probe["option_a"]
                    self.assertIsNotNone(selected)
                    seen_ids.add(selected["puzzle_id"])
                    primary_sphere = selected["sphere"]
                else:
                    self.assertIsNotNone(probe["puzzle"])
                    seen_ids.add(probe["puzzle"]["id"])

        self.assertEqual(
            modes,
            ["choice", "puzzle", "puzzle", "puzzle", "puzzle"],
        )
        self.assertEqual(probe_numbers, [1, 2, 3, 4, 5])

    def test_probe_after_cold_start_is_empty(self):
        self.assertEqual(get_probe(5, set(), "mathematics", grade=6), {})


class PilotRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_pilot_learner_does_not_grant_consent(self):
        """register_pilot_learner only creates the identity/profile — consent
        must never be a silent side effect of registration."""
        conn = _FakeConn()
        learner_id = str(uuid.uuid4()).upper()

        async def fake_get_pool():
            return _FakePool(conn)

        with patch.object(identity, "get_pool", fake_get_pool):
            ok = await identity.register_pilot_learner(learner_id, "", 7)
            self.assertTrue(ok)
            self.assertFalse(
                await identity.check_consent(
                    learner_id,
                    identity.SCOPE_AI_INTERACTION,
                )
            )

        canonical_id = str(uuid.UUID(learner_id))
        self.assertEqual(conn.profiles[canonical_id]["name"], "Student")
        self.assertEqual(conn.profiles[canonical_id]["grade"], 7)

    async def test_grant_pilot_consent_requires_existing_identity(self):
        """Consent can't be granted for a learner who was never registered —
        there must be a real (pilot) identity behind the grant."""
        conn = _FakeConn()
        learner_id = str(uuid.uuid4()).upper()

        async def fake_get_pool():
            return _FakePool(conn)

        with patch.object(identity, "get_pool", fake_get_pool):
            ok = await identity.grant_pilot_consent(learner_id)
            self.assertFalse(ok)
            self.assertFalse(
                await identity.check_consent(
                    learner_id,
                    identity.SCOPE_AI_INTERACTION,
                )
            )

    async def test_register_then_grant_consent_is_explicit_two_step(self):
        """The real flow: register the identity, then a separate, deliberate
        grant_pilot_consent() call is what actually unlocks data collection."""
        conn = _FakeConn()
        learner_id = str(uuid.uuid4()).upper()

        async def fake_get_pool():
            return _FakePool(conn)

        with patch.object(identity, "get_pool", fake_get_pool):
            await identity.register_pilot_learner(learner_id, "Aarav", 6)
            self.assertFalse(
                await identity.check_consent(learner_id, identity.SCOPE_AI_INTERACTION)
            )

            ok = await identity.grant_pilot_consent(learner_id)
            self.assertTrue(ok)
            self.assertTrue(
                await identity.check_consent(learner_id, identity.SCOPE_AI_INTERACTION)
            )
            self.assertTrue(
                await identity.check_consent(learner_id, identity.SCOPE_LEARNER_DATA)
            )


if __name__ == "__main__":
    unittest.main()
