"""
Mailer tests, offline: message construction, deterministic Message-ID, quoted
reply stripping, and the fail-closed configuration rule. No SMTP, no IMAP.

    python -m pytest agents/tests/test_mailer.py -q
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agents.lib import mailer as M  # noqa: E402


class TestMessageConstruction(unittest.TestCase):
    def setUp(self):
        self.box = M.GmailMailbox(user="partnerships@example.test", app_password="x", from_name="Suit Up Swim")

    def test_message_id_is_deterministic_from_attempt_id(self):
        a = M.message_id_for("11111111-2222-3333-4444-555555555555", "example.test")
        b = M.message_id_for("11111111-2222-3333-4444-555555555555", "example.test")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("<swim-") and a.endswith("@example.test>"))

    def test_built_message_carries_our_message_id_and_attempt_header(self):
        msg = self.box.build(to="cj@example.test", subject="Hello", body="Body text", attempt_id="abc-123")
        self.assertEqual(msg["Message-ID"], "<swim-abc-123@example.test>")
        self.assertEqual(msg["X-Swim-Attempt-Id"], "abc-123")
        self.assertEqual(msg["To"], "cj@example.test")
        self.assertIn("Suit Up Swim", msg["From"])
        self.assertEqual(msg.get_content().strip(), "Body text")

    def test_reply_threads_with_in_reply_to(self):
        msg = self.box.build(to="a@example.test", subject="Re: x", body="b", attempt_id="z",
                             in_reply_to="<swim-first@example.test>")
        self.assertEqual(msg["In-Reply-To"], "<swim-first@example.test>")
        self.assertEqual(msg["References"], "<swim-first@example.test>")

    def test_extra_headers_are_added(self):
        msg = self.box.build(to="a@example.test", subject="s", body="b", attempt_id="z",
                             extra_headers={"X-Swim-Test-Intended-Recipient": "dana@fixture.example"})
        self.assertEqual(msg["X-Swim-Test-Intended-Recipient"], "dana@fixture.example")


class TestQuotedReplyStripping(unittest.TestCase):
    def test_strips_quoted_original(self):
        text = "Yes, Tuesday works.\n\nOn Mon, Nov 3, 2026 at 9:00 AM Cameron wrote:\n> My name is Cameron\n> and I run"
        self.assertEqual(M.strip_quoted_reply(text), "Yes, Tuesday works.")

    def test_keeps_text_when_nothing_is_quoted(self):
        self.assertEqual(M.strip_quoted_reply("Plain answer"), "Plain answer")

    def test_never_returns_empty_for_a_fully_quoted_mail(self):
        text = "> only quoted\n> lines"
        self.assertEqual(M.strip_quoted_reply(text), text.strip())


class TestFailClosedConfig(unittest.TestCase):
    def test_from_env_refuses_without_credentials(self):
        saved = {k: os.environ.pop(k, None) for k in ("SWIM_SMTP_USER", "SWIM_SMTP_APP_PASSWORD")}
        try:
            with self.assertRaises(M.MailerConfigError):
                M.GmailMailbox.from_env()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_from_env_strips_spaces_in_app_password(self):
        os.environ["SWIM_SMTP_USER"] = "u@example.test"
        os.environ["SWIM_SMTP_APP_PASSWORD"] = "abcd efgh ijkl mnop"
        try:
            box = M.GmailMailbox.from_env()
            self.assertEqual(box.app_password, "abcdefghijklmnop")
            self.assertEqual(box.domain, "example.test")
        finally:
            os.environ.pop("SWIM_SMTP_USER", None)
            os.environ.pop("SWIM_SMTP_APP_PASSWORD", None)


if __name__ == "__main__":
    unittest.main()
