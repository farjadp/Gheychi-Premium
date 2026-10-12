"""
UserBot peer cache after a redeploy.

The client runs in memory, so every restart empties Pyrogram's peer cache and a
private channel the account belongs to still resolves to CHANNEL_INVALID. The
first miss must warm the cache from the dialog list and retry, and a channel
the account is not in must read as access denied, not a generic failure.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from userbot_client import TGContent, UserBotClient  # noqa: E402


class FakeClient:
    def __init__(self, fail_times: int, message="msg"):
        self.fail_times = fail_times
        self.message = message
        self.get_messages_calls = 0
        self.dialogs_walked = 0

    async def get_messages(self, chat_id, message_id):
        self.get_messages_calls += 1
        if self.get_messages_calls <= self.fail_times:
            raise Exception("Telegram says: [400 CHANNEL_INVALID] - The channel parameter is invalid")
        return self.message

    async def get_dialogs(self):
        self.dialogs_walked += 1
        if False:
            yield None


def make_userbot(fake):
    ub = UserBotClient()
    ub._client = fake
    ub._started = True
    return ub


class PeerCacheWarmupTests(unittest.TestCase):
    def test_first_miss_warms_dialogs_and_retries(self):
        fake = FakeClient(fail_times=1)
        ub = make_userbot(fake)
        got = asyncio.run(ub._get_message_with_peer_warmup(-1001234, 5))
        self.assertEqual(got, "msg")
        self.assertEqual(fake.dialogs_walked, 1)
        self.assertEqual(fake.get_messages_calls, 2)

    def test_still_invalid_after_warmup_is_access_denied(self):
        fake = FakeClient(fail_times=2)
        ub = make_userbot(fake)
        result = asyncio.run(ub.fetch_content("https://t.me/c/1234/5"))
        self.assertIsInstance(result, TGContent)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "access_denied")
        self.assertEqual(fake.dialogs_walked, 1)

    def test_unrelated_errors_do_not_trigger_warmup(self):
        class Boom(FakeClient):
            async def get_messages(self, chat_id, message_id):
                self.get_messages_calls += 1
                raise Exception("Telegram says: [400 MESSAGE_ID_INVALID]")

        fake = Boom(fail_times=0)
        ub = make_userbot(fake)
        result = asyncio.run(ub.fetch_content("https://t.me/c/1234/5"))
        self.assertEqual(result.error, "invalid_link")
        self.assertEqual(fake.dialogs_walked, 0)


if __name__ == "__main__":
    unittest.main()
