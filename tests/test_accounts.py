"""Tests for the account model — mainly the refusals, which are the whole point."""
import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AccountModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls.tmp.name
        import runtime_store
        from pathlib import Path
        # Point the store at a scratch database so tests never touch real data.
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "test.db"
        runtime_store.DATA_DIR = Path(cls.tmp.name)
        runtime_store.init_logs_db()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        import runtime_store
        with runtime_store._connect() as conn:
            for t in ("accounts", "account_telegram_links", "link_cooldowns", "bot_users"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def _plan(self, tg_id, plan_code):
        import runtime_store
        runtime_store.upsert_bot_user(tg_id, username=None, first_name=None, last_name=None, language_code="en")
        with runtime_store._connect() as conn:
            conn.execute("UPDATE bot_users SET plan_code = ? WHERE telegram_user_id = ?", (plan_code, tg_id))
            conn.commit()

    def test_email_is_normalised_so_case_cannot_fork_an_account(self):
        import accounts
        a = accounts.create_account("Farjad@Gmail.COM ")
        self.assertEqual(a["email"], "farjad@gmail.com")
        self.assertEqual(accounts.get_account_by_email("FARJAD@gmail.com")["account_id"], a["account_id"])

    def test_link_and_lookup_roundtrip(self):
        import accounts
        a = accounts.create_account("a@x.com")
        accounts.link_telegram(a["account_id"], 111)
        self.assertEqual(accounts.get_account_by_telegram(111)["account_id"], a["account_id"])
        self.assertEqual(len(accounts.list_links(a["account_id"])), 1)

    def test_relinking_to_the_same_account_is_refused_distinctly(self):
        import accounts
        a = accounts.create_account("a@x.com")
        accounts.link_telegram(a["account_id"], 111)
        with self.assertRaises(accounts.AlreadyLinkedHere):
            accounts.link_telegram(a["account_id"], 111)

    def test_a_telegram_account_cannot_belong_to_two_accounts(self):
        import accounts
        a = accounts.create_account("a@x.com")
        b = accounts.create_account("b@y.com")
        accounts.link_telegram(a["account_id"], 111)
        with self.assertRaises(accounts.OwnedByAnotherAccount) as ctx:
            accounts.link_telegram(b["account_id"], 111)
        # The owner is identifiable to themselves but not disclosed to a stranger.
        self.assertEqual(ctx.exception.masked_email, "a***@x.com")

    def test_free_tier_allows_exactly_one_slot(self):
        import accounts
        a = accounts.create_account("a@x.com")
        accounts.link_telegram(a["account_id"], 111)
        with self.assertRaises(accounts.SlotCapReached) as ctx:
            accounts.link_telegram(a["account_id"], 222)
        self.assertEqual(ctx.exception.cap, 1)

    def test_pro_tier_allows_three_slots(self):
        import accounts
        a = accounts.create_account("a@x.com")
        self._plan(111, "pro")
        accounts.link_telegram(a["account_id"], 111)
        accounts.link_telegram(a["account_id"], 222)
        accounts.link_telegram(a["account_id"], 333)
        with self.assertRaises(accounts.SlotCapReached):
            accounts.link_telegram(a["account_id"], 444)

    def test_a_freed_slot_is_on_cooldown_for_another_telegram_account(self):
        import accounts
        a = accounts.create_account("a@x.com")
        self._plan(111, "pro")
        accounts.link_telegram(a["account_id"], 111)
        accounts.link_telegram(a["account_id"], 222)
        self.assertTrue(accounts.unlink_telegram(a["account_id"], 222))
        # Passing the seat to a different Telegram account has to wait.
        with self.assertRaises(accounts.CooldownActive):
            accounts.link_telegram(a["account_id"], 333)

    def test_the_same_telegram_account_can_be_relinked_immediately(self):
        import accounts
        a = accounts.create_account("a@x.com")
        self._plan(111, "pro")
        accounts.link_telegram(a["account_id"], 111)
        accounts.link_telegram(a["account_id"], 222)
        accounts.unlink_telegram(a["account_id"], 222)
        # Unlinking your own device by mistake should not lock you out for a week.
        accounts.link_telegram(a["account_id"], 222)
        self.assertEqual(len(accounts.list_links(a["account_id"])), 2)

    def test_unlinking_something_not_linked_reports_false(self):
        import accounts
        a = accounts.create_account("a@x.com")
        self.assertFalse(accounts.unlink_telegram(a["account_id"], 999))

    def test_account_plan_is_the_best_among_linked_accounts(self):
        import accounts
        a = accounts.create_account("a@x.com")
        self._plan(111, "pro")
        self._plan(222, "free")
        accounts.link_telegram(a["account_id"], 111)
        accounts.link_telegram(a["account_id"], 222)
        self.assertEqual(accounts.account_plan_code(a["account_id"]), "pro")
        cap = accounts.link_capacity(a["account_id"])
        self.assertEqual((cap["used"], cap["cap"], cap["remaining"]), (2, 3, 1))

    def test_an_account_can_exist_before_it_has_an_email(self):
        import accounts
        a = accounts.create_account()
        self.assertIsNone(a["email"])
        accounts.link_telegram(a["account_id"], 111)
        accounts.set_account_email(a["account_id"], "Later@X.com")
        self.assertEqual(accounts.get_account(a["account_id"])["email"], "later@x.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
