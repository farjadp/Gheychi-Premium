"""
Status-message edits on the Telegram link path.

Telegram rejects an edit that leaves the text unchanged with "Message is not
modified". That error used to escape into the send path and turn a file that
was already sitting in the dump channel into "download failed".
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tg_link_handler import _safe_edit  # noqa: E402


class FakeStatus:
    def __init__(self):
        self.text = None
        self.edits = 0

    async def edit_text(self, text):
        if text == self.text:
            raise Exception("Message is not modified: specified new message content and reply markup are exactly the same")
        self.text = text
        self.edits += 1


class SafeEditTests(unittest.TestCase):
    def test_same_text_twice_does_not_raise(self):
        status = FakeStatus()
        asyncio.run(_safe_edit(status, "sending"))
        asyncio.run(_safe_edit(status, "sending"))
        self.assertEqual(status.text, "sending")
        self.assertEqual(status.edits, 1)

    def test_other_edit_errors_do_not_raise_either(self):
        class Gone(FakeStatus):
            async def edit_text(self, text):
                raise Exception("Message to edit not found")

        asyncio.run(_safe_edit(Gone(), "sending"))

    def test_dump_branch_no_longer_edits_twice(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tg_link_handler.py")).read()
        branch = src.split("if content.dump_message_ids and content.dump_chat_id:", 1)[1].split("elif", 1)[0]
        self.assertNotIn("edit_text", branch)


if __name__ == "__main__":
    unittest.main()
