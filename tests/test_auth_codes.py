"""Tests for one-time codes — the attempt ceiling and replay are what matter."""
import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AuthCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        import runtime_store
        from pathlib import Path
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "test.db"
        runtime_store.DATA_DIR = Path(cls.tmp.name)
        runtime_store.init_logs_db()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        import runtime_store
        with runtime_store._connect() as conn:
            conn.execute("DELETE FROM auth_codes")
            conn.commit()

    def test_a_correct_code_verifies_once_and_never_again(self):
        import auth_codes as ac
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", code)
        with self.assertRaises(ac.CodeInvalid):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", code)

    def test_the_code_is_not_stored_in_the_clear(self):
        import auth_codes as ac, runtime_store
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        with runtime_store._connect() as conn:
            stored = conn.execute("SELECT code_hash FROM auth_codes").fetchone()[0]
        self.assertNotIn(code, stored)
        self.assertEqual(len(stored), 64)

    def test_a_wrong_code_burns_an_attempt_and_the_sixth_is_dead(self):
        import auth_codes as ac
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        for _ in range(ac.MAX_ATTEMPTS):
            with self.assertRaises(ac.CodeInvalid):
                ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", "000000")
        # Right code, but the budget is spent — brute force must not pay off.
        with self.assertRaises(ac.CodeExhausted):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", code)

    def test_an_expired_code_is_refused(self):
        import auth_codes as ac
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", ttl_seconds=-1)
        with self.assertRaises(ac.CodeExpired):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", code)

    def test_issuing_again_invalidates_the_previous_code(self):
        import auth_codes as ac
        first = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        second = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        with self.assertRaises(ac.CodeInvalid):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", first)
        ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com", second)

    def test_a_code_for_one_subject_does_not_work_for_another(self):
        import auth_codes as ac
        code = ac.issue_code(ac.PURPOSE_EMAIL_LOGIN, "a@x.com")
        with self.assertRaises(ac.CodeInvalid):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "b@y.com", code)

    def test_purposes_do_not_cross(self):
        import auth_codes as ac
        # A six-digit link code must never be usable as an email login.
        code = ac.issue_code(ac.PURPOSE_LINK_CODE, "acct-1")
        with self.assertRaises(ac.CodeInvalid):
            ac.verify_code(ac.PURPOSE_EMAIL_LOGIN, "acct-1", code)

    def test_a_deep_link_token_resolves_to_its_subject_once(self):
        import auth_codes as ac
        token = ac.generate_token()
        ac.issue_code(ac.PURPOSE_LINK_DEEP, "acct-1", code=token)
        self.assertEqual(ac.resolve_token(ac.PURPOSE_LINK_DEEP, token), "acct-1")
        self.assertIsNone(ac.resolve_token(ac.PURPOSE_LINK_DEEP, token))

    def test_an_expired_deep_link_token_resolves_to_nothing(self):
        import auth_codes as ac
        token = ac.generate_token()
        ac.issue_code(ac.PURPOSE_LINK_DEEP, "acct-1", code=token, ttl_seconds=-1)
        self.assertIsNone(ac.resolve_token(ac.PURPOSE_LINK_DEEP, token))

    def test_the_deep_link_token_fits_a_telegram_start_payload(self):
        import auth_codes as ac
        # Telegram caps the /start payload at 64 characters, and ours is
        # prefixed with "link_".
        self.assertLessEqual(len("link_" + ac.generate_token()), 64)

    def test_generated_codes_are_six_digits(self):
        import auth_codes as ac
        for _ in range(50):
            c = ac.generate_numeric_code()
            self.assertEqual(len(c), 6)
            self.assertTrue(c.isdigit())


if __name__ == "__main__":
    unittest.main(verbosity=2)
