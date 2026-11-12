"""
A revoked userbot session.

When Telegram drops the session's auth key (AUTH_KEY_UNREGISTERED, SESSION_REVOKED…)
every t.me link fails until the session string is regenerated. The user must be
told the feature is unavailable, not "try again", and the client must stop
claiming it is ready so later requests fail fast.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tg_link_handler import _map_error_to_text  # noqa: E402
from locales import get_text  # noqa: E402
from userbot_client import UserBotClient  # noqa: E402


class DeadSessionClient:
    def __init__(self, err):
        self.err = err
        self.dialogs_walked = 0

    async def get_messages(self, chat_id, message_id):
        raise Exception(self.err)

    async def get_dialogs(self):
        self.dialogs_walked += 1
        if False:
            yield None


def make_userbot(fake):
    ub = UserBotClient()
    ub._client = fake
    ub._started = True
    return ub


class DeadSessionTests(unittest.TestCase):
    def test_auth_key_unregistered_is_session_dead(self):
        fake = DeadSessionClient(
            'Telegram says: [401 AUTH_KEY_UNREGISTERED] - The key is not registered '
            'in the system. (caused by "channels.GetChannels")'
        )
        ub = make_userbot(fake)
        result = asyncio.run(ub.fetch_content("https://t.me/c/4369619770/12"))
        self.assertFalse(result.success)
        self.assertEqual(result.error, "userbot_session_dead")
        self.assertFalse(ub.is_ready)
        self.assertTrue(ub.session_dead)

    def test_session_revoked_is_session_dead(self):
        ub = make_userbot(DeadSessionClient("Telegram says: [401 SESSION_REVOKED]"))
        result = asyncio.run(ub.fetch_content("https://t.me/somechannel/5"))
        self.assertEqual(result.error, "userbot_session_dead")
        self.assertFalse(ub.is_ready)

    def test_dead_session_maps_to_unavailable_text(self):
        for lang in ("fa", "en"):
            text = _map_error_to_text("userbot_session_dead", lang)
            self.assertEqual(text, get_text("tg_userbot_unavailable", lang))
            self.assertNotEqual(text, get_text("tg_download_failed", lang))


if __name__ == "__main__":
    unittest.main()
