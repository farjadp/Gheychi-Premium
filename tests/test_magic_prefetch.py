"""
Regression tests for the link-preview crawler burning a single-use magic link.

Production log, 2026-09-07:
  01:15:17  "TelegramBot (like TwitterBot)"  -> 302   token spent
  01:15:23  "Mozilla/5.0 (iPhone ...) Safari" -> 401   user locked out
"""
import os
import sys
import secrets
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TELEGRAM_CRAWLER = "TelegramBot (like TwitterBot)"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/26.6.1 Mobile/23G83 Safari/604.1")


class MagicLinkPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["ADMIN_PASSWORD"] = "test-admin-pw"
        import runtime_store
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "prefetch.db"
        runtime_store.DATA_DIR = Path(cls.tmp.name)
        runtime_store.init_logs_db()
        import admin_panel
        admin_panel.app.config["TESTING"] = True
        cls.ap = admin_panel

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        import runtime_store
        with runtime_store._connect() as conn:
            for t in ("accounts", "account_telegram_links", "consumed_auth_tokens",
                      "rate_limits", "bot_users", "link_cooldowns"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()
        runtime_store.upsert_bot_user(425864094, username="u", first_name="F",
                                      last_name=None, language_code="fa")

    def _token(self):
        from itsdangerous import URLSafeTimedSerializer
        from config import FLASK_SECRET_KEY
        ser = URLSafeTimedSerializer(FLASK_SECRET_KEY)
        return ser.dumps({"uid": 425864094, "jti": secrets.token_urlsafe(16)}, salt="magic-link")

    def test_the_telegram_crawler_does_not_spend_the_token(self):
        """The exact sequence that locked the user out, replayed."""
        token = self._token()
        crawler = self.ap.app.test_client()
        r1 = crawler.get(f"/auth/magic?token={token}", headers={"User-Agent": TELEGRAM_CRAWLER})
        self.assertEqual(r1.status_code, 200)

        user = self.ap.app.test_client()
        r2 = user.get(f"/auth/magic?token={token}", headers={"User-Agent": IPHONE})
        self.assertEqual(r2.status_code, 302, "the human must still be able to sign in")
        self.assertIn("/dashboard", r2.headers.get("Location", ""))

    def test_the_crawler_is_never_handed_a_session(self):
        token = self._token()
        crawler = self.ap.app.test_client()
        crawler.get(f"/auth/magic?token={token}", headers={"User-Agent": TELEGRAM_CRAWLER})
        with crawler.session_transaction() as sess:
            self.assertIsNone(sess.get("account_id"))
            self.assertIsNone(sess.get("role"))
        # And it stays locked out of everything a session would open.
        self.assertEqual(crawler.get("/account/links").status_code, 401)

    def test_a_real_browser_still_burns_the_token_once(self):
        token = self._token()
        first = self.ap.app.test_client()
        self.assertEqual(first.get(f"/auth/magic?token={token}", headers={"User-Agent": IPHONE}).status_code, 302)
        second = self.ap.app.test_client()
        self.assertEqual(second.get(f"/auth/magic?token={token}", headers={"User-Agent": IPHONE}).status_code, 401)

    def test_other_common_preview_crawlers_are_recognised(self):
        for agent in ("WhatsApp/2.23", "facebookexternalhit/1.1", "Slackbot-LinkExpanding 1.0",
                      "Discordbot/2.0", "Twitterbot/1.0", "LinkedInBot/1.0"):
            with self.subTest(agent=agent):
                self.assertTrue(self.ap._is_link_prefetch(agent))

    def test_ordinary_browsers_are_not_mistaken_for_crawlers(self):
        for agent in (IPHONE,
                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0 Safari/537.36",
                      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/155.0",
                      ""):
            with self.subTest(agent=agent):
                self.assertFalse(self.ap._is_link_prefetch(agent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
