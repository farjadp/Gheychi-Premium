"""
End-to-end tests for the two entry routes.

The point of these is convergence: a user who arrives through the bot and a
user who signs up by email must end up on ONE account, whichever order they do
it in. That is the case most likely to silently produce duplicate identities.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AccountFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["ADMIN_PASSWORD"] = "test-admin-pw"
        import runtime_store
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "test.db"
        runtime_store.DATA_DIR = Path(cls.tmp.name)
        runtime_store.init_logs_db()
        import admin_panel
        admin_panel.app.config["TESTING"] = True
        cls.admin_panel = admin_panel

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        import runtime_store
        with runtime_store._connect() as conn:
            for t in ("accounts", "account_telegram_links", "link_cooldowns",
                      "auth_codes", "bot_users", "rate_limits", "consumed_auth_tokens"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()
        self.client = self.admin_panel.app.test_client()

    # ---- helpers ---------------------------------------------------------
    def _csrf(self):
        self.client.get("/account")
        with self.client.session_transaction() as sess:
            return sess.get("csrf_token")

    def _sign_in_by_email(self, email):
        import auth_codes as ac
        from accounts import normalise_email
        csrf = self._csrf()
        r = self.client.post("/auth/email/request", data={"email": email, "csrf_token": csrf})
        self.assertEqual(r.status_code, 200)
        # The code is hashed at rest, so the test cannot read the one the route
        # issued; it mints its own for the same subject. The subject must be
        # normalised exactly as the route does, or this silently tests nothing.
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, normalise_email(email))
        r = self.client.post("/auth/email/verify",
                             data={"email": email, "code": code, "csrf_token": csrf})
        self.assertEqual(r.status_code, 200, r.data)
        return r

    def _magic_link(self, telegram_user_id):
        import secrets
        from itsdangerous import URLSafeTimedSerializer
        from config import FLASK_SECRET_KEY
        ser = URLSafeTimedSerializer(FLASK_SECRET_KEY)
        token = ser.dumps({"uid": telegram_user_id, "jti": secrets.token_urlsafe(16)}, salt="magic-link")
        return self.client.get(f"/auth/magic?token={token}")

    # ---- tests -----------------------------------------------------------
    def test_email_request_never_reveals_whether_an_account_exists(self):
        csrf = self._csrf()
        unknown = self.client.post("/auth/email/request", data={"email": "nobody@x.com", "csrf_token": csrf})
        self._sign_in_by_email("known@x.com")
        csrf = self._csrf()
        known = self.client.post("/auth/email/request", data={"email": "known@x.com", "csrf_token": csrf})
        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.get_json(), known.get_json())

    def test_a_failed_code_does_not_create_an_account(self):
        import accounts
        csrf = self._csrf()
        self.client.post("/auth/email/request", data={"email": "a@x.com", "csrf_token": csrf})
        r = self.client.post("/auth/email/verify",
                             data={"email": "a@x.com", "code": "000000", "csrf_token": csrf})
        self.assertEqual(r.status_code, 401)
        self.assertIsNone(accounts.get_account_by_email("a@x.com"))

    def test_email_signin_creates_exactly_one_account_and_is_idempotent(self):
        import accounts
        self._sign_in_by_email("a@x.com")
        first = accounts.get_account_by_email("a@x.com")["account_id"]
        self.client.get("/auth/logout")
        self._sign_in_by_email("A@X.com")
        self.assertEqual(accounts.get_account_by_email("a@x.com")["account_id"], first)

    def test_bot_first_user_gets_an_account_automatically(self):
        import accounts, runtime_store
        runtime_store.upsert_bot_user(555, username="u", first_name="U", last_name=None, language_code="en")
        r = self._magic_link(555)
        self.assertEqual(r.status_code, 302)
        account = accounts.get_account_by_telegram(555)
        self.assertIsNotNone(account)
        self.assertIsNone(account["email"])

    def test_bot_first_then_email_converges_on_one_account(self):
        """The case that would otherwise strand a paying user on two identities."""
        import accounts, auth_codes as ac, runtime_store
        runtime_store.upsert_bot_user(555, username="u", first_name="U", last_name=None, language_code="en")
        self._magic_link(555)
        bot_account = accounts.get_account_by_telegram(555)["account_id"]

        # Same person now signs up on the site and links that Telegram account.
        self.client.get("/auth/logout")
        self._sign_in_by_email("a@x.com")
        email_account = accounts.get_account_by_email("a@x.com")["account_id"]
        self.assertNotEqual(bot_account, email_account)

        # Linking must be refused, naming the account that already holds it,
        # rather than silently moving the Telegram account (and its plan).
        with self.assertRaises(accounts.OwnedByAnotherAccount):
            accounts.link_telegram(email_account, 555)

    def test_email_first_then_bot_magic_link_reuses_the_linked_account(self):
        import accounts, runtime_store
        self._sign_in_by_email("a@x.com")
        account_id = accounts.get_account_by_email("a@x.com")["account_id"]
        runtime_store.upsert_bot_user(555, username="u", first_name="U", last_name=None, language_code="en")
        accounts.link_telegram(account_id, 555)

        # Arriving later through the bot must land on the same account.
        self.client.get("/auth/logout")
        self._magic_link(555)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("account_id"), account_id)

    def test_link_start_returns_a_deep_link_and_a_code(self):
        self._sign_in_by_email("a@x.com")
        csrf = self._csrf()
        r = self.client.post("/account/link/start", data={"csrf_token": csrf})
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertIn("?start=link_", body["deep_link"])
        self.assertTrue(body["code"].isdigit())
        self.assertLessEqual(len(body["deep_link"].split("start=")[1]), 64)

    def test_the_deep_link_token_resolves_to_the_issuing_account(self):
        import accounts, auth_codes as ac
        self._sign_in_by_email("a@x.com")
        account_id = accounts.get_account_by_email("a@x.com")["account_id"]
        csrf = self._csrf()
        body = self.client.post("/account/link/start", data={"csrf_token": csrf}).get_json()
        token = body["deep_link"].split("start=link_")[1]
        self.assertEqual(ac.resolve_token(ac.PURPOSE_LINK_DEEP, token), account_id)

    def test_link_endpoints_reject_a_signed_out_visitor(self):
        csrf = self._csrf()
        self.assertEqual(self.client.post("/account/link/start", data={"csrf_token": csrf}).status_code, 401)
        self.assertEqual(self.client.get("/account/links").status_code, 401)

    def test_an_admin_session_is_not_a_user_session(self):
        self.client.post("/login", data={"password": "test-admin-pw"})
        # The admin cookie must not open the account endpoints.
        self.assertEqual(self.client.get("/account/links").status_code, 401)

    def test_unlink_then_relink_a_different_account_is_refused_for_a_week(self):
        import accounts, runtime_store
        self._sign_in_by_email("a@x.com")
        account_id = accounts.get_account_by_email("a@x.com")["account_id"]
        for tg in (111, 222):
            runtime_store.upsert_bot_user(tg, username=None, first_name=None, last_name=None, language_code="en")
        with runtime_store._connect() as conn:
            conn.execute("UPDATE bot_users SET plan_code='pro'")
            conn.commit()
        accounts.link_telegram(account_id, 111)
        accounts.link_telegram(account_id, 222)
        csrf = self._csrf()
        r = self.client.post("/account/unlink", data={"telegram_user_id": "222", "csrf_token": csrf})
        self.assertTrue(r.get_json()["success"])
        with self.assertRaises(accounts.CooldownActive):
            accounts.link_telegram(account_id, 333)


if __name__ == "__main__":
    unittest.main(verbosity=2)
