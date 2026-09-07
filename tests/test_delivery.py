"""Tests for capturing delivery details and resending from the panel."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Media:
    def __init__(self, file_id): self.file_id = file_id


class _Chat:
    def __init__(self, cid): self.id = cid


class _Message:
    """Stands in for what python-telegram-bot hands back from a send."""
    def __init__(self, message_id, chat_id, **media):
        self.message_id = message_id
        self.chat = _Chat(chat_id)
        for k in ("video", "audio", "document", "voice", "animation"):
            setattr(self, k, _Media(media[k]) if k in media else None)


class _MessageId:
    """copy_message returns only this — no chat, no file."""
    def __init__(self, message_id): self.message_id = message_id


class DeliveryDetailTests(unittest.TestCase):
    def test_a_video_send_yields_a_reusable_file_id(self):
        import bot
        d = bot.delivery_details(_Message(42, 999, video="AgAC-video-id"), file_size=1234)
        self.assertEqual(d["message_id"], 42)
        self.assertEqual(d["chat_id"], 999)
        self.assertEqual(d["file_id"], "AgAC-video-id")
        self.assertEqual(d["kind"], "video")
        self.assertEqual(d["file_size_bytes"], 1234)

    def test_an_audio_send_is_recognised_as_audio(self):
        import bot
        d = bot.delivery_details(_Message(7, 8, audio="CQAC-audio-id"))
        self.assertEqual((d["kind"], d["file_id"]), ("audio", "CQAC-audio-id"))

    def test_a_document_send_is_recognised(self):
        import bot
        d = bot.delivery_details(_Message(7, 8, document="BQAC-doc-id"))
        self.assertEqual(d["kind"], "document")

    def test_a_copied_large_file_keeps_its_dump_origin_instead_of_a_file_id(self):
        import bot
        # copy_message gives back no file, so the only way to resend it is to
        # copy from the dump channel again.
        d = bot.delivery_details(_MessageId(55), file_size=900_000_000, source=(-100123, 77))
        self.assertEqual(d["message_id"], 55)
        self.assertIsNone(d.get("file_id"))
        self.assertEqual((d["source_chat_id"], d["source_message_id"]), (-100123, 77))

    def test_a_missing_message_does_not_explode(self):
        import bot
        # A send that failed in an unexpected way must not take the usage
        # record down with it.
        d = bot.delivery_details(None, file_size=10)
        self.assertEqual(d, {"file_size_bytes": 10})


class DeliveryPersistenceTests(unittest.TestCase):
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

    def test_delivery_details_survive_a_round_trip(self):
        import runtime_store
        runtime_store.upsert_bot_user(555, username=None, first_name=None, last_name=None, language_code="en")
        runtime_store.record_usage_event(
            555, platform="YouTube", url="https://y/1", media_kind="video", quality="best",
            duration_seconds=60,
            delivery={"chat_id": 555, "message_id": 42, "file_id": "F1", "kind": "video", "file_size_bytes": 2048},
        )
        with runtime_store._connect() as conn:
            row = conn.execute(
                "SELECT delivery_chat_id, delivery_message_id, delivery_file_id, delivery_kind, file_size_bytes"
                " FROM usage_events ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row, (555, 42, "F1", "video", 2048))

    def test_a_record_without_delivery_details_still_works(self):
        import runtime_store
        runtime_store.upsert_bot_user(556, username=None, first_name=None, last_name=None, language_code="en")
        # Every row written before this feature shipped looks like this, and the
        # panel has to cope rather than showing a broken button.
        runtime_store.record_usage_event(556, platform="YouTube", url="https://y/2", media_kind="video")
        with runtime_store._connect() as conn:
            row = conn.execute(
                "SELECT delivery_file_id, file_size_bytes FROM usage_events WHERE telegram_user_id = 556").fetchone()
        self.assertEqual(row, (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ResendEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["ADMIN_PASSWORD"] = "test-admin-pw"
        import runtime_store
        runtime_store.LOGS_DB = Path(cls.tmp.name) / "resend.db"
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
            for t in ("accounts", "account_telegram_links", "usage_events", "bot_users",
                      "rate_limits", "link_cooldowns"):
                conn.execute(f"DELETE FROM {t}")
            conn.commit()
        self.client = self.ap.app.test_client()

    def _signed_in_account(self, tg_ids):
        import accounts, runtime_store
        a = accounts.create_account("a@x.com")
        for tg in tg_ids:
            runtime_store.upsert_bot_user(tg, username=None, first_name=None, last_name=None, language_code="en")
        with runtime_store._connect() as conn:
            conn.execute("UPDATE bot_users SET plan_code='pro'")
            conn.commit()
        for tg in tg_ids:
            accounts.link_telegram(a["account_id"], tg)
        self.client.get("/account")
        with self.client.session_transaction() as sess:
            sess["role"] = self.ap.ROLE_USER
            sess["account_id"] = a["account_id"]
            sess["csrf_token"] = "tok"
        return a["account_id"]

    def _event(self, tg, **delivery):
        import runtime_store
        runtime_store.record_usage_event(tg, platform="YouTube", url="https://y/1",
                                         media_kind="video", delivery=delivery or None)
        with runtime_store._connect() as conn:
            return conn.execute("SELECT MAX(id) FROM usage_events").fetchone()[0]

    def test_a_signed_out_visitor_cannot_resend(self):
        self.assertEqual(
            self.client.post("/account/resend", data={"event_id": "1", "csrf_token": "x"}).status_code, 403)

    def test_you_cannot_resend_another_accounts_file(self):
        """Event ids are sequential integers, so ownership must be checked."""
        import accounts, runtime_store
        stranger = accounts.create_account("other@x.com")
        runtime_store.upsert_bot_user(888, username=None, first_name=None, last_name=None, language_code="en")
        accounts.link_telegram(stranger["account_id"], 888)
        theirs = self._event(888, chat_id=888, message_id=1, file_id="SECRET", kind="video")

        self._signed_in_account([111])
        r = self.client.post("/account/resend", data={"event_id": str(theirs), "csrf_token": "tok"})
        # Reported as not found, not as forbidden — a 403 would confirm the row exists.
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not_found")

    def test_an_event_without_delivery_details_is_refused_clearly(self):
        self._signed_in_account([111])
        old = self._event(111)
        r = self.client.post("/account/resend", data={"event_id": str(old), "csrf_token": "tok"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"], "no_delivery_record")

    def test_history_marks_which_rows_can_be_resent(self):
        import stats
        acct = self._signed_in_account([111])
        self._event(111)
        self._event(111, chat_id=111, message_id=9, file_id="F1", kind="video")
        self._event(111, chat_id=111, message_id=10, source_chat_id=-100123, source_message_id=5)
        rows = {r["id"]: r for r in stats.account_history(acct)}
        flags = sorted(r["can_resend"] for r in rows.values())
        self.assertEqual(flags, [False, True, True])

    def test_a_jump_link_is_only_offered_when_the_message_is_known(self):
        import stats
        acct = self._signed_in_account([111])
        self._event(111)
        self._event(111, chat_id=111, message_id=9, file_id="F1", kind="video")
        links = sorted((r["jump_link"] or "") for r in stats.account_history(acct))
        self.assertEqual(links[0], "")
        self.assertIn("tg://openmessage?chat_id=111&message_id=9", links[1])
