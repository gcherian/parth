"""
Tests for modules.survey.routes — token issuance/verification round trip,
with the DB pool mocked (no real network I/O).
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jwt

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from config import Config
from modules.survey import routes as survey_routes


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.opened_tokens = set()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "UPDATE teacher.survey_links SET opened_at" in sql:
            self.opened_tokens.add(args[0])


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


class SurveyTokenTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_verify_round_trip(self):
        conn = _FakeConn()
        with patch.object(survey_routes, "get_pool", AsyncMock(return_value=_FakePool(conn))):
            resp = await survey_routes.create_survey_link(
                survey_routes.SurveyLinkRequest(school_id="dav-school-1", teacher_phone="+911234567890")
            )

        self.assertTrue(resp["url"].startswith("/teacher/form?token="))
        token = resp["url"].split("token=")[1]

        claims = await survey_routes.verify_survey_token(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["school_id"], "dav-school-1")
        self.assertEqual(claims["teacher_phone"], "+911234567890")

        # exactly one INSERT into teacher.survey_links happened
        insert_calls = [c for c in conn.executed if "INSERT INTO teacher.survey_links" in c[0]]
        self.assertEqual(len(insert_calls), 1)

    async def test_expired_token_fails_verification(self):
        payload = {
            "jti": "x", "school_id": "s1", "teacher_phone": None,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, Config.SURVEY_LINK_SECRET, algorithm="HS256")
        claims = await survey_routes.verify_survey_token(token)
        self.assertIsNone(claims)

    async def test_tampered_token_fails_verification(self):
        claims = await survey_routes.verify_survey_token("not-a-real-token")
        self.assertIsNone(claims)

    async def test_mark_opened_updates_only_matching_token(self):
        conn = _FakeConn()
        with patch.object(survey_routes, "get_pool", AsyncMock(return_value=_FakePool(conn))):
            await survey_routes.mark_survey_link_opened("some-token")
        self.assertIn("some-token", conn.opened_tokens)


if __name__ == "__main__":
    unittest.main()
