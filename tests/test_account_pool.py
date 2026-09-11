"""
Model C, phase 2: the plan and the quota belong to the account.

A Telegram account linked to a web account gets the best active plan among the
Telegram accounts linked there, and every linked ID draws on one quota pool.
One that is not linked behaves exactly as it did before accounts existed.
"""
import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AccountPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls.tmp.name
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
            for t in ("accounts", "account_telegram_links", "link_cooldowns", "bot_users", "usage_events"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    # helpers
    def _user(self, tg, plan=None):
        import runtime_store
        runtime_store.upsert_bot_user(tg, language_code="en")
        if plan:
            runtime_store.assign_user_plan(tg, plan)

    def _use(self, tg, platform, n):
        import runtime_store
        for _ in range(n):
            runtime_store.record_usage_event(tg, platform=platform)

    def _account(self, *tgs):
        import accounts
        a = accounts.create_account()
        for tg in tgs:
            accounts.link_telegram(a["account_id"], tg)
        return a["account_id"]

    # tests
    def test_an_unlinked_telegram_account_behaves_as_before(self):
        import runtime_store
        self._user(501, "standard")
        self._use(501, "YouTube", 3)
        user = runtime_store.get_bot_user(501)
        self.assertEqual(user["effective_plan_code"], "standard")
        self.assertIsNone(user["account_id"])
        self.assertEqual(runtime_store.count_usage_events(501, platform="YouTube", period="month"), 3)

    def test_paying_on_one_linked_account_covers_the_others(self):
        import runtime_store
        self._user(601, "standard"); self._user(602)
        self._account(601, 602)
        user = runtime_store.get_bot_user(602)
        self.assertEqual(user["effective_plan_code"], "standard")
        self.assertTrue(user["plan_via_account"])
        self.assertEqual(user["plan_code"], "free", "the second account's own assignment is untouched")

    def test_an_expired_plan_does_not_cover_anyone(self):
        import accounts, runtime_store
        self._user(701, "pro"); self._user(702)
        aid = self._account(701)
        with runtime_store._connect() as conn:
            past = (runtime_store._utc_datetime() - timedelta(days=1)).isoformat()
            conn.execute("UPDATE bot_users SET plan_expires_at = ? WHERE telegram_user_id = 701", (past,))
            conn.commit()
        self.assertEqual(accounts.account_plan_code(aid), "free")
        self.assertEqual(runtime_store.get_bot_user(701)["effective_plan_code"], "free")

    def test_linked_accounts_share_one_quota(self):
        import runtime_store
        self._user(801, "standard"); self._user(802)
        self._account(801, 802)
        self._use(801, "YouTube", 6); self._use(802, "YouTube", 4)   # Standard: 10 YouTube a month
        for tg in (801, 802):
            self.assertEqual(runtime_store.count_usage_events(tg, platform="YouTube", period="month"), 10)
            self.assertFalse(runtime_store.evaluate_download_access(tg, platform="YouTube")["allowed"])

    def test_unlinking_does_not_hand_usage_back(self):
        import accounts, runtime_store
        self._user(901, "standard"); self._user(902)
        aid = self._account(901, 902)
        self._use(901, "YouTube", 6); self._use(902, "YouTube", 4)
        accounts.unlink_telegram(aid, 902)
        self.assertEqual(runtime_store.count_usage_events(901, platform="YouTube", period="month"), 10)
        self.assertFalse(runtime_store.evaluate_download_access(901, platform="YouTube")["allowed"])

    def test_linking_brings_earlier_usage_into_the_pool(self):
        import runtime_store
        self._user(1001, "standard"); self._user(1002)
        self._use(1002, "YouTube", 3)                                   # spent before it was linked
        self._account(1001, 1002)
        self._use(1001, "YouTube", 7)
        self.assertEqual(runtime_store.count_usage_events(1001, platform="YouTube", period="month"), 10)

    def test_the_other_sites_allowance_is_pooled_too(self):
        import runtime_store
        from config import OTHER_SITES_PLATFORM
        self._user(1101, "standard"); self._user(1102)
        self._account(1101, 1102)
        self._use(1101, "BiliBili", 2); self._use(1102, "Bandcamp", 1)
        # Built here rather than read from plans.json, which other test modules
        # share and may have rewritten: this test is about the pool, not the plans.
        rule = {"platform": OTHER_SITES_PLATFORM, "limit": 13, "period": "month"}
        self.assertEqual(runtime_store.count_rule_usage(1101, rule), 3)
        self.assertEqual(runtime_store.count_rule_usage(1102, rule), 3)


if __name__ == "__main__":
    unittest.main()
