"""
Tests for foundation.notify_transport — channel adapter dispatch, with
SMTP/Twilio calls mocked (no real network I/O).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from foundation import notify_transport as nt


class ChannelRegistryTests(unittest.TestCase):
    def test_all_three_channels_registered(self):
        self.assertEqual(set(nt.CHANNELS.keys()), {"email", "sms", "whatsapp"})


class SendEmailTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_smtp_config_fails_closed(self):
        with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_USER": ""}, clear=False):
            ok = await nt.send_email("a@b.com", "Subject", "Body")
            self.assertFalse(ok)

    async def test_configured_smtp_sends(self):
        env = {
            "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587",
            "SMTP_USER": "user", "SMTP_PASS": "pass", "SMTP_FROM": "parth@example.com",
        }
        fake_smtp = MagicMock()
        fake_smtp.__enter__.return_value = fake_smtp
        with patch.dict("os.environ", env, clear=False), \
             patch("smtplib.SMTP", return_value=fake_smtp):
            ok = await nt.send_email("a@b.com", "Subject", "Body")
        self.assertTrue(ok)
        fake_smtp.sendmail.assert_called_once()


class SendWhatsAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_whatsapp_config_fails_closed(self):
        with patch.dict("os.environ", {"TWILIO_WHATSAPP_FROM": ""}, clear=False):
            ok = await nt.send_whatsapp("+911234567890", "hello")
            self.assertFalse(ok)

    async def test_configured_whatsapp_sends_with_prefix(self):
        env = {
            "TWILIO_SID": "sid", "TWILIO_TOKEN": "token",
            "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        }
        fake_client = MagicMock()
        fake_client_cls = MagicMock(return_value=fake_client)
        with patch.dict("os.environ", env, clear=False), \
             patch("twilio.rest.Client", fake_client_cls):
            ok = await nt.send_whatsapp("+911234567890", "hello")
        self.assertTrue(ok)
        _, kwargs = fake_client.messages.create.call_args
        self.assertEqual(kwargs["to"], "whatsapp:+911234567890")
        self.assertEqual(kwargs["from_"], "whatsapp:+14155238886")


if __name__ == "__main__":
    unittest.main()
