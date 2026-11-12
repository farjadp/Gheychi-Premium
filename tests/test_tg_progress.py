"""
Progress for slow restricted-content transfers.

A 40 MB file took ~8 minutes to download and ~4 to upload on the userbot, while
the status message sat on "Downloading..." and looked stuck. Pyrogram reports
(current, total) per chunk; the bot must turn that into a percentage without
editing the status message on every chunk (Telegram rate-limits edits).
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tg_link_handler import _progress_text  # noqa: E402
from userbot_client import make_transfer_progress  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ThrottleTests(unittest.TestCase):
    def run_calls(self, calls, interval=5.0):
        events = []
        clock = FakeClock()

        async def cb(stage, current=None, total=None):
            events.append((stage, current, total))

        progress = make_transfer_progress(cb, "downloading", interval=interval, clock=clock)

        async def go():
            for t, current, total in calls:
                clock.now = t
                await progress(current, total)

        asyncio.run(go())
        return events

    def test_first_chunk_is_reported(self):
        events = self.run_calls([(0, 1, 100)])
        self.assertEqual(events, [("downloading", 1, 100)])

    def test_rapid_chunks_are_throttled(self):
        events = self.run_calls([(0, 1, 100), (1, 2, 100), (2, 3, 100), (6, 4, 100)])
        self.assertEqual([e[1] for e in events], [1, 4])

    def test_last_chunk_is_always_reported(self):
        events = self.run_calls([(0, 1, 100), (1, 100, 100)])
        self.assertEqual([e[1] for e in events], [1, 100])

    def test_no_callback_means_no_progress(self):
        self.assertIsNone(make_transfer_progress(None, "downloading"))

    def test_callback_errors_do_not_break_the_transfer(self):
        async def broken(stage, current=None, total=None):
            raise RuntimeError("edit failed")

        progress = make_transfer_progress(broken, "downloading", clock=FakeClock())
        asyncio.run(progress(1, 100))  # must not raise


class ProgressTextTests(unittest.TestCase):
    def test_download_text_has_percent_and_megabytes(self):
        mb = 1024 * 1024
        text = _progress_text("downloading", 17 * mb, 40 * mb, "en")
        self.assertIn("42%", text)
        self.assertIn("17.0 / 40.0 MB", text)

    def test_upload_stage_uses_its_own_text(self):
        mb = 1024 * 1024
        down = _progress_text("downloading", mb, 2 * mb, "fa")
        up = _progress_text("uploading_to_dump", mb, 2 * mb, "fa")
        self.assertNotEqual(down.splitlines()[-2], up.splitlines()[-2])

    def test_unknown_total_does_not_divide_by_zero(self):
        text = _progress_text("downloading", 5, 0, "en")
        self.assertNotIn("%", text)


if __name__ == "__main__":
    unittest.main()
