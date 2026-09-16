"""
Persian for Persian speakers, English for everyone else.

The rule this pins down: nothing Persian ever reaches a user whose language is
not Persian. Before this, get_text fell back to Persian for any unknown code,
so a German user saw a Persian bot.
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PERSIAN = re.compile(r"[؀-ۿ]")


class LanguageResolutionTests(unittest.TestCase):
    def test_only_persian_codes_resolve_to_persian(self):
        from locales import normalize_lang
        for code in ("fa", "fa-IR", "FA_ir", " fa "):
            self.assertEqual(normalize_lang(code), "fa", code)
        for code in ("en", "en-GB", "de", "ru", "ar", "tr", "", None, "farsi-ish"):
            self.assertEqual(normalize_lang(code), "en", code)

    def test_a_user_with_no_stored_language_gets_english(self):
        from locales import user_lang_of
        self.assertEqual(user_lang_of(None), "en")
        self.assertEqual(user_lang_of({}), "en")
        self.assertEqual(user_lang_of({"language_code": None}), "en")
        self.assertEqual(user_lang_of({"language_code": "de"}), "en")
        self.assertEqual(user_lang_of({"language_code": "fa"}), "fa")

    def test_an_unknown_language_falls_back_to_english_not_persian(self):
        from locales import MESSAGES, get_text
        for key in list(MESSAGES["en"])[:40]:
            self.assertEqual(get_text(key, "de"), get_text(key, "en"), key)


class EnglishStaysEnglishTests(unittest.TestCase):
    def test_no_english_message_contains_persian(self):
        from locales import MESSAGES
        bad = {k: v for k, v in MESSAGES["en"].items() if PERSIAN.search(str(v))}
        self.assertEqual(bad, {}, "English messages must not carry Persian text")

    def test_both_languages_define_the_same_keys(self):
        from locales import MESSAGES
        self.assertEqual(set(MESSAGES["fa"]), set(MESSAGES["en"]))

    def test_plan_names_and_period_words_follow_the_reader(self):
        from plans import get_plan, period_label, plan_display_name
        plan = get_plan("starter")
        self.assertFalse(PERSIAN.search(plan_display_name(plan, "en")))
        self.assertTrue(PERSIAN.search(plan_display_name(plan, "fa")))
        self.assertEqual(period_label("month", "en"), "month")
        self.assertTrue(PERSIAN.search(period_label("month", "fa")))


class QuotaRefusalsFollowTheUserTests(unittest.TestCase):
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

    def _refusal(self, tg, lang, platform="Facebook"):
        import runtime_store
        runtime_store.upsert_bot_user(tg, language_code=lang)
        access = runtime_store.evaluate_download_access(tg, platform=platform)
        self.assertFalse(access["allowed"], "Facebook is Pro-only, so Free must refuse it")
        return access["reason"]

    def test_an_english_user_is_refused_in_english(self):
        reason = self._refusal(31001, "en")
        self.assertFalse(PERSIAN.search(reason), f"got Persian: {reason!r}")
        self.assertIn("Facebook", reason)

    def test_a_german_user_is_also_refused_in_english(self):
        reason = self._refusal(31002, "de")
        self.assertFalse(PERSIAN.search(reason), f"got Persian: {reason!r}")

    def test_a_persian_user_is_refused_in_persian(self):
        reason = self._refusal(31003, "fa")
        self.assertTrue(PERSIAN.search(reason), f"expected Persian: {reason!r}")

    def test_a_used_up_allowance_reads_in_the_users_language(self):
        import runtime_store
        for tg, lang in ((31004, "en"), (31005, "fa")):
            runtime_store.upsert_bot_user(tg, language_code=lang)
            for _ in range(5):                       # Free: 5 Instagram a month
                runtime_store.record_usage_event(tg, platform="Instagram")
            reason = runtime_store.evaluate_download_access(tg, platform="Instagram")["reason"]
            self.assertFalse(reason is None)
            if lang == "en":
                self.assertFalse(PERSIAN.search(reason), f"got Persian: {reason!r}")
                self.assertIn("5/5", reason)
            else:
                self.assertTrue(PERSIAN.search(reason), f"expected Persian: {reason!r}")


class ActivationMessageTests(unittest.TestCase):
    def _message(self, lang):
        os.environ.setdefault("ADMIN_PASSWORD", "test-only")
        try:
            from admin_panel import _format_payment_success_message
        except Exception as exc:
            self.skipTest(f"admin_panel not importable here: {exc}")
        from plans import get_plan
        user = {"language_code": lang, "plan_expires_at": "2026-12-01T00:00:00+00:00"}
        return _format_payment_success_message(user, get_plan("starter"))

    def test_an_english_buyer_gets_only_english(self):
        msg = self._message("en")
        self.assertFalse(PERSIAN.search(msg), f"Persian in an English confirmation: {msg!r}")
        self.assertIn("Starter", msg)

    def test_a_persian_buyer_gets_only_persian_plus_the_numbers(self):
        msg = self._message("fa")
        self.assertTrue(PERSIAN.search(msg))
        self.assertNotIn("Your plan is active", msg)


if __name__ == "__main__":
    unittest.main()
