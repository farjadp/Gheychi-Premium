"""Tests for history categorisation and the peer comparison."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        import runtime_store
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "test.db"
        runtime_store.DATA_DIR = Path(cls.tmp.name)
        runtime_store.init_logs_db()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        import runtime_store
        with runtime_store._connect() as conn:
            for t in ("accounts", "account_telegram_links", "usage_events", "bot_users", "link_cooldowns"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()

    def _event(self, tg, platform, kind="video", when="2026-09-05T10:00:00+00:00", secs=60):
        import runtime_store
        with runtime_store._connect() as conn:
            conn.execute(
                """INSERT INTO usage_events (telegram_user_id, created_at, plan_code, platform,
                   url, media_kind, quality, duration_seconds)
                   VALUES (?,?,'free',?,?,?,?,?)""",
                (tg, when, platform, f"https://x/{platform}", kind, kind, secs),
            )
            conn.commit()

    def _account_with(self, email, tg_ids):
        import accounts, runtime_store
        a = accounts.create_account(email)
        for tg in tg_ids:
            runtime_store.upsert_bot_user(tg, username=None, first_name=None, last_name=None, language_code="en")
        with runtime_store._connect() as conn:
            conn.execute("UPDATE bot_users SET plan_code='pro'")
            conn.commit()
        for tg in tg_ids:
            accounts.link_telegram(a["account_id"], tg)
        return a["account_id"]

    def test_history_spans_every_linked_telegram_account(self):
        import stats
        acct = self._account_with("a@x.com", [111, 222])
        self._event(111, "YouTube")
        self._event(222, "Instagram")
        history = stats.account_history(acct)
        self.assertEqual(len(history), 2)
        self.assertEqual({h["category"] for h in history}, {"video", "social"})

    def test_an_account_with_no_links_has_empty_history(self):
        import accounts, stats
        a = accounts.create_account("none@x.com")
        self.assertEqual(stats.account_history(a["account_id"]), [])
        self.assertEqual(stats.account_stats(a["account_id"])["total"], 0)

    def test_audio_from_a_video_site_files_under_audio(self):
        import stats
        acct = self._account_with("a@x.com", [111])
        self._event(111, "YouTube", kind="audio")
        self.assertEqual(stats.account_history(acct)[0]["category"], "audio")

    def test_telegram_keeps_its_own_bucket_even_for_audio(self):
        import stats
        acct = self._account_with("a@x.com", [111])
        self._event(111, "Telegram", kind="audio")
        self.assertEqual(stats.account_history(acct)[0]["category"], "telegram")

    def test_category_summary_is_stable_and_complete(self):
        import categories, stats
        acct = self._account_with("a@x.com", [111])
        self._event(111, "YouTube")
        summary = stats.account_stats(acct)["by_category"]
        # Every category is always present and always in the same order, so the
        # filter bar does not reshuffle as the user downloads things.
        self.assertEqual([c["category"] for c in summary], categories.CATEGORY_ORDER)

    def test_comparison_is_withheld_when_there_are_too_few_peers(self):
        import stats
        acct = self._account_with("a@x.com", [111])
        self._event(111, "YouTube")
        comparison = stats.account_stats(acct)["comparison"]
        self.assertFalse(comparison["available"])

    def test_comparison_appears_once_there_are_enough_peers(self):
        import stats
        mine = self._account_with("me@x.com", [1000])
        for i in range(10):
            tg = 2000 + i
            other = self._account_with(f"p{i}@x.com", [tg])
            self._event(tg, "YouTube")
        # Ten downloads puts this account above every peer, who have one each.
        for _ in range(10):
            self._event(1000, "YouTube")
        c = stats.account_stats(mine)["comparison"]
        self.assertTrue(c["available"])
        self.assertGreaterEqual(c["percentile"], 90)
        self.assertTrue(c["more_than_median"])

    def test_everyone_on_zero_is_not_told_they_beat_everyone(self):
        import stats
        mine = self._account_with("me@x.com", [1000])
        for i in range(10):
            self._account_with(f"p{i}@x.com", [2000 + i])
        c = stats.account_stats(mine)["comparison"]
        # All tied at zero: the midpoint of the tied band is 50, not 100.
        self.assertEqual(c["percentile"], 50)

    def test_comparison_never_leaks_another_account(self):
        import stats
        mine = self._account_with("me@x.com", [1000])
        for i in range(10):
            self._account_with(f"p{i}@x.com", [2000 + i])
        c = stats.account_stats(mine)["comparison"]
        self.assertEqual(set(c) - {"available", "peer_count", "percentile", "median", "more_than_median"}, set())

    def test_minutes_saved_and_busiest_day(self):
        import stats
        acct = self._account_with("a@x.com", [111])
        self._event(111, "YouTube", when="2026-09-05T10:00:00+00:00", secs=120)
        self._event(111, "YouTube", when="2026-09-05T11:00:00+00:00", secs=120)
        self._event(111, "Vimeo", when="2026-09-01T11:00:00+00:00", secs=60)
        s = stats.account_stats(acct)
        self.assertEqual(s["minutes_saved"], 5)
        self.assertEqual(s["busiest_day"], {"date": "2026-09-05", "count": 2})
        self.assertEqual(s["top_category"], "video")


if __name__ == "__main__":
    unittest.main(verbosity=2)
